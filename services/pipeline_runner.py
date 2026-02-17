"""Pipeline Runner — 在后台线程中执行完整流水线。"""

import logging
import os
import threading
import time

from models.task_models import (
    FileState,
    FileStatus,
    Stage,
    Task,
    TaskStatus,
)

logger = logging.getLogger(__name__)

PROGRESS_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "progress.json")


def run_pipeline(task: Task, cancel: threading.Event):
    """在后台线程中执行完整流水线。

    调用方（TaskManager）负责捕获顶层异常。
    """
    cfg = task.config_snapshot
    task.status = TaskStatus.RUNNING
    task.started_at = time.time()
    task.stage = Stage.INIT
    task.add_event("info", "init", "task_started", "流水线启动")

    def _check_cancel():
        if cancel.is_set():
            raise _CancelledError("任务被取消")

    try:
        _check_cancel()

        # ---- Stage: Zotero Collect ----
        task.stage = Stage.ZOTERO_COLLECT
        task.add_event("info", "zotero_collect", "stage_enter", "开始收集 Zotero 附件")

        from zotero_client import check_connection, collect_files
        if not check_connection(cfg):
            raise RuntimeError("无法连接 Zotero MCP 服务")

        from progress import load_progress
        progress = load_progress(PROGRESS_FILE)

        from dify_client import (
            get_or_create_dataset,
            get_dataset_info,
            get_dataset_document_name_index,
            get_dataset_document_total,
        )

        dataset_id = get_or_create_dataset(cfg)
        dataset_info = get_dataset_info(cfg, dataset_id)
        remote_name_index = get_dataset_document_name_index(cfg, dataset_id)
        dataset_doc_total = remote_name_index.get("total")
        if dataset_doc_total is None:
            dataset_doc_total = get_dataset_document_total(cfg, dataset_id)
            remote_name_index["total"] = dataset_doc_total
        if dataset_doc_total is not None:
            task.add_event("info", "zotero_collect", "dataset_doc_total", f"目标知识库文档总数：{dataset_doc_total}")

        should_save_progress = False
        conflict_count = _clean_conflict_processed_records(progress, dataset_id)
        if conflict_count:
            should_save_progress = True
            task.add_event(
                "warn",
                "zotero_collect",
                "progress_conflict_cleaned",
                f"检测到 {conflict_count} 条 processed/failed 冲突记录，已清理后重试",
            )

        stale_count, stale_reason = _reconcile_processed_records_with_remote(
            progress,
            dataset_id,
            remote_name_index,
        )
        if stale_count:
            should_save_progress = True
            if stale_reason == "empty-dataset":
                task.add_event(
                    "warn",
                    "zotero_collect",
                    "stale_processed_cleaned",
                    f"目标知识库为空，已清理 {stale_count} 条本地 processed 记录并允许重传",
                )
            else:
                task.add_event(
                    "warn",
                    "zotero_collect",
                    "stale_processed_cleaned",
                    f"已按远端文档名索引清理 {stale_count} 条本地 processed 记录",
                )
        elif stale_reason == "no-prefixed-item-key":
            task.add_event(
                "info",
                "zotero_collect",
                "remote_name_index_unavailable",
                "远端文档名不含 [item_key] 前缀，已跳过按名称清理",
            )

        if should_save_progress:
            from progress import save_progress
            save_progress(progress, PROGRESS_FILE)

        file_map = collect_files(
            cfg,
            progress_processed=progress["processed"],
            collection_keys=task.collection_keys or None,
            recursive=cfg.get("zotero", {}).get("collection_recursive", True),
            page_size=cfg.get("zotero", {}).get("collection_page_size", 50),
            target_dataset=dataset_id,
        )

        if not file_map:
            task.add_event("info", "zotero_collect", "no_files", "没有新文件需要处理")
            task.status = TaskStatus.SUCCEEDED
            task.finished_at = time.time()
            return

        # 初始化文件状态
        for fpath, tkey in file_map.items():
            task.files.append(FileState(filename=os.path.basename(fpath)))

        task.add_event("info", "zotero_collect", "files_collected", f"收集到 {len(file_map)} 个文件")
        _check_cancel()

        # ---- Stage: MinerU Upload + Poll ----
        task.stage = Stage.MINERU_UPLOAD
        task.add_event("info", "mineru_upload", "stage_enter", "开始 MinerU 批量解析")

        from mineru_client import process_files
        md_results, md_failures = process_files(cfg, file_map)

        for key, reason in md_failures.items():
            progress["failed"][key] = {"stage": "mineru", "reason": reason}
            _update_file_status(task, key, file_map, FileStatus.FAILED, Stage.MINERU_POLL, str(reason))

        if md_failures:
            from progress import save_progress
            save_progress(progress, PROGRESS_FILE)

        task.add_event(
            "info", "mineru_poll", "mineru_done",
            f"MinerU 解析完成：成功 {len(md_results)}，失败 {len(md_failures)}"
        )
        _check_cancel()

        if not md_results:
            task.add_event("warn", "mineru_poll", "no_results", "没有文件成功解析")
            task.status = TaskStatus.FAILED
            task.error = "MinerU 解析全部失败"
            task.finished_at = time.time()
            return

        # ---- Stage: MD Clean ----
        task.stage = Stage.MD_CLEAN
        task.add_event("info", "md_clean", "stage_enter", "开始清洗 Markdown")

        from md_cleaner import clean_all
        md_results, clean_stats = clean_all(md_results, cfg)

        task.add_event(
            "info", "md_clean", "clean_done",
            f"清洗完成：原始 {clean_stats['total_original']} 字符 -> {clean_stats['total_cleaned']} 字符"
        )
        _check_cancel()

        # ---- Stage: Smart Split ----
        task.stage = Stage.SMART_SPLIT
        smart_cfg = cfg.get("smart_split", {})
        if smart_cfg.get("enabled", True):
            task.add_event("info", "smart_split", "stage_enter", "开始智能分割")

            from splitter import smart_split_all
            md_results, split_stats = smart_split_all(md_results, cfg)

            task.add_event(
                "info", "smart_split", "split_done",
                f"智能分割完成：{split_stats['total_splits']} 个分割点"
            )
        else:
            task.add_event("info", "smart_split", "skipped", "智能分割已禁用")
        _check_cancel()

        # ---- Stage: Dify Upload ----
        task.stage = Stage.DIFY_UPLOAD
        task.add_event("info", "dify_upload", "stage_enter", f"开始上传 {len(md_results)} 篇文档到 Dify")

        # 智能分割开启时，强制 separator 为 split_marker
        effective_cfg = cfg
        if smart_cfg.get("enabled", True):
            import json
            effective_cfg = json.loads(json.dumps(cfg))
            marker = smart_cfg.get("split_marker", "<!--split-->")
            effective_cfg["dify"]["segment_separator"] = marker

        from dify_client import upload_all
        uploaded_keys, upload_failures = upload_all(
            effective_cfg, dataset_id, md_results, dataset_info=dataset_info
        )

        for key in uploaded_keys:
            file_name = md_results.get(key, {}).get("file_name", key)
            progress["processed"][key] = {
                "file_name": file_name,
                "dify_dataset": dataset_id,
            }
            progress["failed"].pop(key, None)
            _update_file_status(task, key, file_map, FileStatus.SUCCEEDED, Stage.DIFY_INDEX)

        for key in upload_failures:
            progress["failed"][key] = {
                "stage": "dify",
                "dify_dataset": dataset_id,
                "reason": "上传或索引失败",
            }
            _update_file_status(task, key, file_map, FileStatus.FAILED, Stage.DIFY_UPLOAD, "上传或索引失败")

        from progress import save_progress
        save_progress(progress, PROGRESS_FILE)

        task.add_event(
            "info", "dify_upload", "upload_done",
            f"Dify 上传完成：成功 {len(uploaded_keys)}，失败 {len(upload_failures)}"
        )

        # ---- Finalize ----
        task.stage = Stage.FINALIZE
        total_failed = len(md_failures) + len(upload_failures)
        if total_failed == 0:
            task.status = TaskStatus.SUCCEEDED
        elif len(uploaded_keys) > 0:
            task.status = TaskStatus.PARTIAL_SUCCEEDED
        else:
            task.status = TaskStatus.FAILED
            task.error = "全部文件处理失败"
        task.finished_at = time.time()
        task.add_event(
            "info", "finalize", "task_finished",
            f"流水线完成：解析 {len(md_results)}/{len(file_map)}，"
            f"上传 {len(uploaded_keys)}/{len(md_results)}"
        )

    except _CancelledError:
        task.status = TaskStatus.CANCELLED
        task.finished_at = time.time()
        task.add_event("warn", task.stage.value, "cancelled", "任务被取消")
    except Exception as exc:
        logger.exception("Pipeline 异常: %s", exc)
        task.status = TaskStatus.FAILED
        task.error = str(exc)
        task.finished_at = time.time()
        task.add_event("error", task.stage.value, "pipeline_error", str(exc))


def _clean_conflict_processed_records(progress: dict, dataset_id: str) -> int:
    """清理同一 dataset 下 failed(dify) 与 processed 冲突记录。"""
    processed = progress.get("processed", {})
    failed = progress.get("failed", {})
    conflict_keys = []

    for key, failed_entry in failed.items():
        if key not in processed:
            continue

        processed_entry = processed[key]
        processed_dataset = processed_entry.get("dify_dataset") if isinstance(processed_entry, dict) else None
        if processed_dataset and processed_dataset != dataset_id:
            continue

        if isinstance(failed_entry, dict):
            failed_stage = failed_entry.get("stage")
            failed_dataset = failed_entry.get("dify_dataset")
            if failed_dataset and failed_dataset != dataset_id:
                continue
            if failed_stage and failed_stage != "dify":
                continue
            conflict_keys.append(key)
            continue

        if isinstance(failed_entry, str) and "dify" in failed_entry.lower():
            conflict_keys.append(key)

    for key in conflict_keys:
        processed.pop(key, None)

    return len(conflict_keys)


def _reconcile_processed_records_with_remote(progress: dict, dataset_id: str, remote_name_index: dict):
    """按远端知识库文档名核验本地 processed，返回 (清理数量, 原因)。"""
    from dify_client import build_markdown_doc_name

    processed = progress.get("processed", {})
    total = remote_name_index.get("total")
    remote_names = set(remote_name_index.get("names") or [])
    remote_item_keys = set(remote_name_index.get("prefixed_item_keys") or [])

    stale_keys = []
    if total == 0:
        for key, entry in processed.items():
            if isinstance(entry, dict) and entry.get("dify_dataset") == dataset_id:
                stale_keys.append(key)
        for key in stale_keys:
            processed.pop(key, None)
        return len(stale_keys), "empty-dataset"

    if not remote_item_keys:
        return 0, "no-prefixed-item-key"

    for key, entry in processed.items():
        if not isinstance(entry, dict):
            continue
        if entry.get("dify_dataset") != dataset_id:
            continue

        processed_key = str(key)
        item_key = processed_key.split("#", 1)[0]
        file_name = entry.get("file_name") or "document"
        expected_name = build_markdown_doc_name(item_key, file_name)

        if expected_name in remote_names:
            continue
        if item_key in remote_item_keys:
            continue
        stale_keys.append(processed_key)

    for key in stale_keys:
        processed.pop(key, None)

    return len(stale_keys), "name-index"


def _update_file_status(
    task: Task,
    key: str,
    file_map: dict,
    status: FileStatus,
    stage: Stage,
    error: str = "",
):
    """根据 task_key 更新对应 FileState。"""
    filename = None
    for fpath, tkey in file_map.items():
        if tkey == key:
            filename = os.path.basename(fpath)
            break
    if filename is None:
        return
    for fs in task.files:
        if fs.filename == filename:
            fs.status = status
            fs.stage = stage
            fs.error = error
            break


class _CancelledError(Exception):
    pass
