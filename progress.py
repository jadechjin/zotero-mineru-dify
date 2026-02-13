import json
import logging
import os

from config import PROGRESS_FILE

logger = logging.getLogger(__name__)


def _empty_progress():
    return {"processed": {}, "failed": {}}


def load_progress():
    if not os.path.exists(PROGRESS_FILE):
        return _empty_progress()

    try:
        with open(PROGRESS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("读取进度文件失败：%s", exc)
        return _empty_progress()

    if not isinstance(data, dict):
        return _empty_progress()

    processed = data.get("processed", {})
    failed = data.get("failed", {})
    if not isinstance(processed, dict) or not isinstance(failed, dict):
        return _empty_progress()

    return {"processed": processed, "failed": failed}


def _entry_matches_dataset(entry, target_dataset=None):
    """判断一条 processed 记录是否属于目标知识库。

    - target_dataset 为空：保持旧行为，认为命中即已处理。
    - entry 为 dict 且包含 dify_dataset：仅当相等时才算已处理。
    - 旧格式（无 dify_dataset）在指定 target_dataset 时不算已处理，
      以支持同一文件上传到不同知识库。
    """
    if not target_dataset:
        return True

    if isinstance(entry, dict):
        entry_dataset = entry.get("dify_dataset")
        if not entry_dataset:
            return False
        return entry_dataset == target_dataset

    return False


def is_processed(progress_processed, item_key, task_key, target_dataset=None):
    """检查某个附件是否已在目标知识库处理过。"""
    if item_key in progress_processed and _entry_matches_dataset(
        progress_processed[item_key], target_dataset
    ):
        return True

    if task_key in progress_processed and _entry_matches_dataset(
        progress_processed[task_key], target_dataset
    ):
        return True

    return False


def save_progress(progress):
    tmp_file = f"{PROGRESS_FILE}.tmp"
    with open(tmp_file, "w", encoding="utf-8") as f:
        json.dump(progress, f, ensure_ascii=False, indent=2)
    os.replace(tmp_file, PROGRESS_FILE)
