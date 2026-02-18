"""Pipeline runner executed in background thread."""
from __future__ import annotations

from collections import defaultdict
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
    """Run full pipeline in a background thread."""
    cfg = task.config_snapshot
    task.status = TaskStatus.RUNNING
    task.started_at = time.time()
    task.stage = Stage.INIT
    task.add_event("info", "init", "task_started", "pipeline started")

    def _check_cancel():
        if cancel.is_set():
            raise _CancelledError("task cancelled")

    try:
        _check_cancel()

        # ---- Stage: Zotero Collect ----
        task.stage = Stage.ZOTERO_COLLECT
        task.add_event("info", "zotero_collect", "stage_enter", "collecting Zotero attachments")

        from zotero_client import check_connection, collect_files

        if not check_connection(cfg):
            raise RuntimeError("cannot connect Zotero MCP service")

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
            task.add_event("info", "zotero_collect", "dataset_doc_total", f"dataset docs total: {dataset_doc_total}")

        should_save_progress = False
        conflict_count = _clean_conflict_processed_records(progress, dataset_id)
        if conflict_count:
            should_save_progress = True
            task.add_event(
                "warn",
                "zotero_collect",
                "progress_conflict_cleaned",
                f"cleaned {conflict_count} processed/failed conflicts",
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
                    f"dataset empty; removed {stale_count} stale processed records",
                )
            else:
                task.add_event(
                    "warn",
                    "zotero_collect",
                    "stale_processed_cleaned",
                    f"removed {stale_count} stale processed records by remote index",
                )
        elif stale_reason == "no-prefixed-item-key":
            task.add_event(
                "info",
                "zotero_collect",
                "remote_name_index_unavailable",
                "remote doc names have no [item_key] prefix; skip name-based cleanup",
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
            task.add_event("info", "zotero_collect", "no_files", "no new files to process")
            task.status = TaskStatus.SUCCEEDED
            task.finished_at = time.time()
            return

        for fpath in file_map.keys():
            task.files.append(FileState(filename=os.path.basename(fpath)))

        task.add_event("info", "zotero_collect", "files_collected", f"collected {len(file_map)} files")
        _check_cancel()

        # ---- Stage: MinerU Upload + Poll ----
        task.stage = Stage.MINERU_UPLOAD
        task.add_event("info", "mineru_upload", "stage_enter", "start MinerU batch parse")

        from mineru_client import process_files

        md_results, md_failures = process_files(cfg, file_map)

        for key, reason in md_failures.items():
            progress["failed"][key] = {"stage": "mineru", "reason": reason}
            _update_file_status(task, key, file_map, FileStatus.FAILED, Stage.MINERU_POLL, str(reason))

        if md_failures:
            from progress import save_progress

            save_progress(progress, PROGRESS_FILE)

        task.add_event(
            "info",
            "mineru_poll",
            "mineru_done",
            f"MinerU done: success={len(md_results)}, failed={len(md_failures)}",
        )
        _check_cancel()

        if not md_results:
            task.add_event("warn", "mineru_poll", "no_results", "no file parsed successfully")
            task.status = TaskStatus.FAILED
            task.error = "all MinerU parses failed"
            task.finished_at = time.time()
            return

        # ---- Stage: MD Clean ----
        task.stage = Stage.MD_CLEAN
        task.add_event("info", "md_clean", "stage_enter", "start markdown cleaning")

        from md_cleaner import clean_all

        md_results, clean_stats = clean_all(md_results, cfg)

        task.add_event(
            "info",
            "md_clean",
            "clean_done",
            f"clean done: {clean_stats['total_original']} -> {clean_stats['total_cleaned']} chars",
        )

        image_ai = clean_stats.get("image_summary") or {}
        task.runtime_stats["image_ai"] = image_ai
        if image_ai.get("enabled") is False:
            task.add_event(
                "info",
                "md_clean",
                "image_ai_disabled",
                "Image AI summary is disabled. Fallback summary mode was used.",
            )
        else:
            total_images = int(image_ai.get("total_images") or 0)
            attempted = int(image_ai.get("ai_attempted") or 0)
            succeeded = int(image_ai.get("ai_succeeded") or 0)
            failed = int(image_ai.get("ai_failed") or 0)
            fallback = int(image_ai.get("fallback_used") or 0)
            level = "warn" if failed > 0 else "info"
            task.add_event(
                level,
                "md_clean",
                "image_ai_summary",
                (
                    "Image AI summary result: "
                    f"total_images={total_images}, attempted={attempted}, "
                    f"succeeded={succeeded}, failed={failed}, fallback={fallback}"
                ),
            )
        _check_cancel()

        # ---- Stage: Smart Split ----
        task.stage = Stage.SMART_SPLIT
        smart_cfg = cfg.get("smart_split", {})
        if smart_cfg.get("enabled", True):
            task.add_event("info", "smart_split", "stage_enter", "start smart split")

            from splitter import smart_split_all

            md_results, split_stats = smart_split_all(md_results, cfg)

            task.add_event(
                "info",
                "smart_split",
                "split_done",
                f"smart split done: split_points={split_stats.get('total_splits', 0)}",
            )
        else:
            task.add_event("info", "smart_split", "skipped", "smart split disabled")

        from splitter import split_documents_for_upload

        # Mandatory doc-level split for upload: each doc must be <= 300k chars.
        md_results, doc_split_stats = split_documents_for_upload(md_results, cfg)
        task.runtime_stats["upload_doc_split"] = doc_split_stats
        task.add_event(
            "info",
            "smart_split",
            "doc_split_done",
            (
                "Upload doc split done: "
                f"source_files={doc_split_stats.get('source_files', 0)}, "
                f"output_docs={doc_split_stats.get('output_docs', 0)}, "
                f"max_chars={doc_split_stats.get('max_chars', 0)}, "
                f"heading_cuts={doc_split_stats.get('heading_cuts', 0)}, "
                f"hard_cuts={doc_split_stats.get('hard_cuts', 0)}"
            ),
        )
        _check_cancel()

        source_doc_count = int(doc_split_stats.get("source_files") or len(file_map))
        upload_doc_count = int(doc_split_stats.get("output_docs") or len(md_results))

        # ---- Stage: Dify Upload ----
        task.stage = Stage.DIFY_UPLOAD
        task.add_event(
            "info",
            "dify_upload",
            "stage_enter",
            f"start uploading {upload_doc_count} docs to Dify from {source_doc_count} source files",
        )

        # Force Dify segment separator when smart split is enabled.
        effective_cfg = cfg
        if smart_cfg.get("enabled", True):
            import json

            effective_cfg = json.loads(json.dumps(cfg))
            marker = smart_cfg.get("split_marker", "<!--split-->")
            effective_cfg["dify"]["segment_separator"] = marker

        from dify_client import upload_all

        parent_part_totals = _build_parent_part_totals(md_results)
        parent_index_ok_counts = defaultdict(int)
        parent_failures = set()
        parent_done_reported = set()

        def _on_dify_progress(payload: dict):
            phase = (payload or {}).get("phase", "")
            item_key = (payload or {}).get("item_key", "")
            message = (payload or {}).get("message", "")
            success = (payload or {}).get("success", None)
            parent_key = _resolve_parent_task_key(md_results, item_key) if item_key else ""

            if phase == "submit_ok":
                if parent_key:
                    _update_file_status(task, parent_key, file_map, FileStatus.PROCESSING, Stage.DIFY_UPLOAD)
                task.add_event("info", "dify_upload", "file_submitted", message or f"submitted to Dify: {item_key}")
                return

            if phase == "submit_failed":
                if parent_key:
                    parent_failures.add(parent_key)
                    _update_file_status(
                        task,
                        parent_key,
                        file_map,
                        FileStatus.FAILED,
                        Stage.DIFY_UPLOAD,
                        message or "Dify submit failed",
                    )
                task.add_event("warn", "dify_upload", "file_submit_failed", message or f"submit failed: {item_key}")
                return

            if phase == "index_wait_begin":
                task.stage = Stage.DIFY_INDEX
                task.add_event("info", "dify_index", "index_wait", message or "waiting Dify indexing")
                return

            if phase == "index_ok":
                if parent_key:
                    parent_index_ok_counts[parent_key] += 1
                    expected_parts = int(parent_part_totals.get(parent_key, 1))
                    if (
                        parent_key not in parent_failures
                        and parent_index_ok_counts[parent_key] >= expected_parts
                        and parent_key not in parent_done_reported
                    ):
                        parent_done_reported.add(parent_key)
                        _update_file_status(task, parent_key, file_map, FileStatus.SUCCEEDED, Stage.DIFY_INDEX)
                task.add_event("info", "dify_index", "file_indexed", message or f"index done: {item_key}")
                return

            if phase == "index_failed":
                if parent_key:
                    parent_failures.add(parent_key)
                    _update_file_status(
                        task,
                        parent_key,
                        file_map,
                        FileStatus.FAILED,
                        Stage.DIFY_INDEX,
                        message or "Dify indexing failed",
                    )
                level = "error" if success is False else "warn"
                task.add_event(level, "dify_index", "file_index_failed", message or f"index failed: {item_key}")
                return

        uploaded_keys, upload_failures = upload_all(
            effective_cfg,
            dataset_id,
            md_results,
            dataset_info=dataset_info,
            progress_callback=_on_dify_progress,
        )

        uploaded_parent_keys, failed_parent_keys = _aggregate_parent_upload_outcomes(
            uploaded_keys,
            upload_failures,
            md_results,
            parent_part_totals,
        )

        for key in sorted(uploaded_parent_keys):
            file_name = _resolve_parent_file_name(md_results, key)
            _clear_parent_progress_entries(progress["processed"], key)
            progress["processed"][key] = {
                "file_name": file_name,
                "dify_dataset": dataset_id,
            }
            _clear_parent_progress_entries(progress["failed"], key)
            _update_file_status(task, key, file_map, FileStatus.SUCCEEDED, Stage.DIFY_INDEX)

        for key in sorted(failed_parent_keys):
            _clear_parent_progress_entries(progress["processed"], key)
            _clear_parent_progress_entries(progress["failed"], key)
            progress["failed"][key] = {
                "stage": "dify",
                "dify_dataset": dataset_id,
                "reason": "upload or indexing failed",
            }
            _update_file_status(
                task,
                key,
                file_map,
                FileStatus.FAILED,
                Stage.DIFY_INDEX,
                "upload or indexing failed",
            )

        from progress import save_progress

        save_progress(progress, PROGRESS_FILE)

        task.add_event(
            "info",
            "dify_upload",
            "upload_done",
            f"Dify upload done: succeeded={len(uploaded_parent_keys)}, failed={len(failed_parent_keys)}",
        )
        if failed_parent_keys:
            task.add_event(
                "warn",
                "dify_index",
                "retry_hint",
                "Some files failed during upload/indexing. Start again to retry failed files; successful files will be skipped.",
            )

        # ---- Finalize ----
        task.stage = Stage.FINALIZE
        total_failed = len(md_failures) + len(failed_parent_keys)
        if total_failed == 0:
            task.status = TaskStatus.SUCCEEDED
        elif uploaded_parent_keys:
            task.status = TaskStatus.PARTIAL_SUCCEEDED
        else:
            task.status = TaskStatus.FAILED
            task.error = "all files failed"
        task.finished_at = time.time()
        task.add_event(
            "info",
            "finalize",
            "task_finished",
            (
                f"pipeline done: parsed {source_doc_count}/{len(file_map)}, "
                f"uploaded {len(uploaded_parent_keys)}/{source_doc_count}"
            ),
        )

    except _CancelledError:
        task.status = TaskStatus.CANCELLED
        task.finished_at = time.time()
        task.add_event("warn", task.stage.value, "cancelled", "task cancelled")
    except Exception as exc:
        logger.exception("Pipeline error: %s", exc)
        task.status = TaskStatus.FAILED
        task.error = str(exc)
        task.finished_at = time.time()
        task.add_event("error", task.stage.value, "pipeline_error", str(exc))


def _clean_conflict_processed_records(progress: dict, dataset_id: str) -> int:
    """Clean processed/failed conflicts for the same dataset."""
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
    """Reconcile local processed records against remote dataset index."""
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


def _resolve_parent_task_key(md_results: dict, item_key: str) -> str:
    data = md_results.get(item_key) if isinstance(md_results, dict) else None
    parent = ""
    if isinstance(data, dict):
        parent = str(data.get("parent_task_key") or "")
    base = parent or str(item_key or "")
    return base.split("#", 1)[0]


def _build_parent_part_totals(md_results: dict) -> dict[str, int]:
    totals = defaultdict(int)
    for item_key in (md_results or {}).keys():
        parent_key = _resolve_parent_task_key(md_results, item_key)
        if parent_key:
            totals[parent_key] += 1
    return dict(totals)


def _resolve_parent_file_name(md_results: dict, parent_key: str) -> str:
    for item_key, data in (md_results or {}).items():
        if _resolve_parent_task_key(md_results, item_key) != parent_key:
            continue
        if isinstance(data, dict):
            source_name = str(data.get("source_file_name") or "").strip()
            if source_name:
                return source_name
            file_name = str(data.get("file_name") or "").strip()
            if file_name:
                return file_name
    return parent_key


def _clear_parent_progress_entries(progress_bucket: dict, parent_key: str):
    if not isinstance(progress_bucket, dict) or not parent_key:
        return

    keys = []
    prefix = f"{parent_key}#part"
    for key in list(progress_bucket.keys()):
        key_str = str(key)
        if key_str == parent_key or key_str.startswith(prefix):
            keys.append(key)

    for key in keys:
        progress_bucket.pop(key, None)


def _aggregate_parent_upload_outcomes(
    uploaded_keys: list[str],
    failed_keys: list[str],
    md_results: dict,
    parent_part_totals: dict[str, int],
) -> tuple[set[str], set[str]]:
    uploaded_parts = defaultdict(set)
    failed_parents = set()

    for key in uploaded_keys or []:
        parent = _resolve_parent_task_key(md_results, key)
        if parent:
            uploaded_parts[parent].add(key)

    for key in failed_keys or []:
        parent = _resolve_parent_task_key(md_results, key)
        if parent:
            failed_parents.add(parent)

    candidate_parents = set(parent_part_totals.keys())
    candidate_parents.update(uploaded_parts.keys())
    candidate_parents.update(failed_parents)

    succeeded = set()
    for parent in candidate_parents:
        if parent in failed_parents:
            continue
        expected_parts = int(parent_part_totals.get(parent, 1))
        if len(uploaded_parts.get(parent, set())) >= expected_parts:
            succeeded.add(parent)
        else:
            failed_parents.add(parent)

    return succeeded, failed_parents


def _update_file_status(
    task: Task,
    key: str,
    file_map: dict,
    status: FileStatus,
    stage: Stage,
    error: str = "",
):
    """Update FileState by task key."""
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
