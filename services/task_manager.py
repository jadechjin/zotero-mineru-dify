"""任务管理器 — 线程安全的任务生命周期管理。"""

import logging
import threading
from typing import Callable

from models.task_models import (
    Task,
    TaskStatus,
    FileStatus,
)

logger = logging.getLogger(__name__)


class TaskManager:
    """管理所有 Pipeline 任务的创建、查询、取消。

    - 维护 tasks dict + RLock
    - 默认 max_concurrent_tasks=1（单线程执行）
    - 支持取消 running/queued 任务
    """

    def __init__(self, max_concurrent: int = 1):
        self._lock = threading.RLock()
        self._tasks: dict[str, Task] = {}
        self._threads: dict[str, threading.Thread] = {}
        self._cancel_flags: dict[str, threading.Event] = {}
        self._skip_files: dict[str, set[str]] = {}  # task_id -> {filename, ...}
        self._max_concurrent = max_concurrent

    def create_task(
        self,
        collection_keys: list[str],
        config_snapshot: dict,
        config_version: int,
    ) -> Task:
        """创建新任务。"""
        with self._lock:
            running = sum(
                1
                for t in self._tasks.values()
                if t.status in (TaskStatus.RUNNING, TaskStatus.QUEUED)
            )
            if running >= self._max_concurrent:
                raise RuntimeError(
                    f"已有 {running} 个任务在运行/排队，上限 {self._max_concurrent}"
                )

            task = Task(
                collection_keys=collection_keys,
                config_snapshot=config_snapshot,
                config_version=config_version,
            )
            self._tasks[task.task_id] = task
            self._cancel_flags[task.task_id] = threading.Event()
            self._skip_files[task.task_id] = set()
            return task

    def start_task(
        self,
        task_id: str,
        runner_fn: Callable[[Task, threading.Event, set], None],
    ):
        """在后台线程中启动任务。"""
        with self._lock:
            task = self._tasks.get(task_id)
            if task is None:
                raise KeyError(f"任务不存在: {task_id}")
            if task.status != TaskStatus.QUEUED:
                raise RuntimeError(f"任务状态非 queued: {task.status}")

            cancel_event = self._cancel_flags[task_id]
            skip_set = self._skip_files[task_id]

            def _run():
                try:
                    runner_fn(task, cancel_event, skip_set)
                except Exception as exc:
                    logger.exception("任务 %s 异常终止", task_id)
                    with self._lock:
                        task.status = TaskStatus.FAILED
                        task.error = str(exc)
                        import time
                        task.finished_at = time.time()
                        task.add_event("error", task.stage.value, "task_error", str(exc))

            thread = threading.Thread(
                target=_run, name=f"task-{task_id}", daemon=True
            )
            self._threads[task_id] = thread
            thread.start()

    def cancel_task(self, task_id: str) -> bool:
        """请求取消任务。"""
        with self._lock:
            task = self._tasks.get(task_id)
            if task is None:
                return False
            if task.status not in (TaskStatus.RUNNING, TaskStatus.QUEUED):
                return False
            flag = self._cancel_flags.get(task_id)
            if flag:
                flag.set()
            task.status = TaskStatus.CANCELLED
            import time
            task.finished_at = time.time()
            task.add_event("warn", task.stage.value, "task_cancelled", "用户取消任务")
            return True

    def skip_file(self, task_id: str, filename: str) -> dict:
        """请求跳过某个文件的后续处理。"""
        with self._lock:
            task = self._tasks.get(task_id)
            if task is None:
                return {"ok": False, "reason": "任务不存在"}
            if task.status not in (TaskStatus.RUNNING, TaskStatus.QUEUED):
                return {"ok": False, "reason": "任务已结束，无法跳过"}

            target_fs = None
            for fs in task.files:
                if fs.filename == filename:
                    target_fs = fs
                    break
            if target_fs is None:
                return {"ok": False, "reason": f"文件不存在: {filename}"}

            if target_fs.status in (FileStatus.SUCCEEDED, FileStatus.FAILED, FileStatus.SKIPPED):
                return {"ok": False, "reason": f"文件已处于终态: {target_fs.status.value}"}

            target_fs.status = FileStatus.SKIPPED
            target_fs.error = "用户手动跳过"

            skip_set = self._skip_files.get(task_id)
            if skip_set is None:
                skip_set = set()
                self._skip_files[task_id] = skip_set
            skip_set.add(filename)

            task.add_event("info", task.stage.value, "file_skipped", f"用户跳过文件: {filename}")
            return {"ok": True, "reason": ""}

    def get_task(self, task_id: str) -> Task | None:
        with self._lock:
            return self._tasks.get(task_id)

    def list_tasks(self) -> list[dict]:
        with self._lock:
            return [t.summary() for t in self._tasks.values()]

    def get_events(self, task_id: str, after_seq: int = 0) -> list[dict]:
        with self._lock:
            task = self._tasks.get(task_id)
            if task is None:
                return []
            return [
                e.to_dict() for e in task.events if e.seq > after_seq
            ]

    def get_files(self, task_id: str) -> list[dict]:
        with self._lock:
            task = self._tasks.get(task_id)
            if task is None:
                return []
            return [f.to_dict() for f in task.files]
