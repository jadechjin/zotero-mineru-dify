"""任务数据模型 — Task / FileState / Event 定义。"""

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum


class TaskStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    PARTIAL_SUCCEEDED = "partial_succeeded"


class Stage(str, Enum):
    INIT = "init"
    ZOTERO_COLLECT = "zotero_collect"
    MINERU_UPLOAD = "mineru_upload"
    MINERU_POLL = "mineru_poll"
    MD_CLEAN = "md_clean"
    SMART_SPLIT = "smart_split"
    DIFY_UPLOAD = "dify_upload"
    DIFY_INDEX = "dify_index"
    FINALIZE = "finalize"


STAGE_ORDER = list(Stage)


class FileStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class FileState:
    filename: str
    status: FileStatus = FileStatus.PENDING
    stage: Stage = Stage.INIT
    error: str = ""
    progress: float = 0.0

    def to_dict(self) -> dict:
        return {
            "filename": self.filename,
            "status": self.status.value,
            "stage": self.stage.value,
            "error": self.error,
            "progress": self.progress,
        }


@dataclass
class Event:
    seq: int
    ts: float
    level: str
    stage: str
    event: str
    message: str

    def to_dict(self) -> dict:
        return {
            "seq": self.seq,
            "ts": self.ts,
            "level": self.level,
            "stage": self.stage,
            "event": self.event,
            "message": self.message,
        }


@dataclass
class Task:
    task_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    status: TaskStatus = TaskStatus.QUEUED
    stage: Stage = Stage.INIT
    created_at: float = field(default_factory=time.time)
    started_at: float | None = None
    finished_at: float | None = None
    collection_keys: list[str] = field(default_factory=list)
    config_snapshot: dict = field(default_factory=dict)
    config_version: int = 0
    files: list[FileState] = field(default_factory=list)
    events: list[Event] = field(default_factory=list)
    runtime_stats: dict = field(default_factory=dict)
    error: str = ""
    _seq_counter: int = field(default=0, repr=False)

    def add_event(
        self, level: str, stage: str, event: str, message: str
    ) -> Event:
        self._seq_counter += 1
        evt = Event(
            seq=self._seq_counter,
            ts=time.time(),
            level=level,
            stage=stage,
            event=event,
            message=message,
        )
        self.events.append(evt)
        return evt

    def summary(self) -> dict:
        total = len(self.files)
        succeeded = sum(1 for f in self.files if f.status == FileStatus.SUCCEEDED)
        failed = sum(1 for f in self.files if f.status == FileStatus.FAILED)
        pending = total - succeeded - failed
        stats = {
            "total": total,
            "succeeded": succeeded,
            "failed": failed,
            "pending": pending,
        }
        if isinstance(self.runtime_stats, dict) and self.runtime_stats:
            stats.update(self.runtime_stats)
        return {
            "task_id": self.task_id,
            "status": self.status.value,
            "stage": self.stage.value,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "collection_keys": self.collection_keys,
            "config_version": self.config_version,
            "error": self.error,
            "stats": stats,
        }

    def detail(self) -> dict:
        d = self.summary()
        d["files"] = [f.to_dict() for f in self.files]
        return d
