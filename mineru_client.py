import io
import logging
import os
import time
import zipfile

import requests

from config import (
    MINERU_API_TOKEN,
    MINERU_BASE_URL,
    MINERU_BATCH_SIZE,
    MINERU_MAX_FILE_SIZE_BYTES,
    MINERU_MODEL_VERSION,
    POLL_INTERVAL_MINERU,
    POLL_TIMEOUT_MINERU,
)

logger = logging.getLogger(__name__)

_HEADERS = {
    "Content-Type": "application/json",
    "Authorization": f"Bearer {MINERU_API_TOKEN}",
}


def _validate_file_size(file_path):
    """Raise ValueError if the file exceeds MinerU's size limit."""
    size = os.path.getsize(file_path)
    if size > MINERU_MAX_FILE_SIZE_BYTES:
        raise ValueError(
            f"File too large: {os.path.basename(file_path)} "
            f"({size} bytes > {MINERU_MAX_FILE_SIZE_BYTES})"
        )


def _request_upload_urls(file_entries):
    """Request pre-signed upload URLs from MinerU.

    Args:
        file_entries: list of {"name": filename, "data_id": item_key}

    Returns:
        (batch_id, file_urls) where file_urls is a list of pre-signed PUT URLs.
    """
    resp = requests.post(
        f"{MINERU_BASE_URL}/file-urls/batch",
        headers=_HEADERS,
        json={"files": file_entries, "model_version": MINERU_MODEL_VERSION},
        timeout=60,
    )
    resp.raise_for_status()
    body = resp.json()

    if body.get("code") != 0:
        raise RuntimeError(f"MinerU file-urls/batch failed: {body}")

    data = body["data"]
    return data["batch_id"], data["file_urls"]


def _upload_file(url, file_path, max_retries=3):
    """PUT a local file to the pre-signed URL with retry logic.

    Retries on network errors, timeouts, HTTP 429, and 5xx.
    Fails immediately on HTTP 4xx (except 429).
    """
    backoff_times = [2, 8, 32]

    for attempt in range(1, max_retries + 1):
        try:
            with open(file_path, "rb") as f:
                resp = requests.put(url, data=f, timeout=600)

            if resp.status_code == 200:
                return

            if resp.status_code == 429 or resp.status_code >= 500:
                raise requests.ConnectionError(
                    f"HTTP {resp.status_code} (retryable)"
                )

            raise RuntimeError(
                f"Upload failed for {os.path.basename(file_path)}: "
                f"HTTP {resp.status_code}"
            )
        except (requests.ConnectionError, requests.Timeout) as exc:
            if attempt < max_retries:
                wait = backoff_times[attempt - 1]
                logger.warning(
                    "上传重试 %d/%d 失败：%s，错误=%s，%d 秒后重试...",
                    attempt, max_retries, os.path.basename(file_path),
                    exc, wait,
                )
                time.sleep(wait)
            else:
                raise RuntimeError(
                    f"Upload failed for {os.path.basename(file_path)} "
                    f"after {max_retries} attempts: {exc}"
                ) from exc


def upload_batch(file_items):
    """Upload a batch of files to MinerU.

    Args:
        file_items: list of (file_path, task_key) tuples. Max 200 per call.

    Returns:
        (batch_id, uploaded_items, failed_items) where:
            uploaded_items = list of (file_path, task_key) that succeeded
            failed_items = list of (task_key, error_msg) that failed.
            batch_id may be empty when all files fail local validation.
    """
    if len(file_items) > MINERU_BATCH_SIZE:
        raise ValueError(
            f"Batch size {len(file_items)} exceeds limit {MINERU_BATCH_SIZE}"
        )

    valid_items = []
    failed_items = []

    for path, key in file_items:
        try:
            _validate_file_size(path)
            valid_items.append((path, key))
        except Exception as exc:
            logger.error(
                "上传前校验失败：%s，错误=%s",
                os.path.basename(path), exc,
            )
            failed_items.append((key, f"validation failed: {exc}"))

    if not valid_items:
        logger.warning(
            "批次跳过：%d/%d 个文件未通过上传前校验",
            len(failed_items), len(file_items),
        )
        return "", [], failed_items

    entries = [
        {"name": os.path.basename(path), "data_id": key}
        for path, key in valid_items
    ]

    batch_id, urls = _request_upload_urls(entries)

    if len(urls) != len(valid_items):
        raise RuntimeError(
            f"MinerU returned {len(urls)} upload URLs for {len(valid_items)} files"
        )

    logger.info("批次 %s：开始上传 %d 个文件", batch_id, len(urls))

    uploaded_items = []

    for i, url in enumerate(urls):
        path, key = valid_items[i]
        try:
            _upload_file(url, path)
            logger.debug("上传完成：%s", os.path.basename(path))
            uploaded_items.append((path, key))
        except Exception as exc:
            logger.error("上传失败：%s，错误=%s", os.path.basename(path), exc)
            failed_items.append((key, str(exc)))

    logger.info(
        "批次 %s 上传结果：成功 %d，失败 %d",
        batch_id, len(uploaded_items), len(failed_items),
    )

    return batch_id, uploaded_items, failed_items


def poll_batch(batch_id, expected_count=None, expected_keys=None):
    """Poll MinerU until all tasks in a batch reach a terminal state.

    Args:
        batch_id: the batch identifier.
        expected_count: if set, consider batch complete when this many
            results reach a terminal state (for partial uploads).
        expected_keys: if set, require these data_id values to reach
            terminal state before returning.

    Returns:
        list of result dicts from the API.

    Raises:
        TimeoutError: if batch does not finish within POLL_TIMEOUT_MINERU seconds.
    """
    start = time.time()
    expected_keys_set = set(expected_keys) if expected_keys else None

    while True:
        if time.time() - start > POLL_TIMEOUT_MINERU:
            raise TimeoutError(
                f"Batch {batch_id} did not finish within {POLL_TIMEOUT_MINERU}s"
            )

        resp = requests.get(
            f"{MINERU_BASE_URL}/extract-results/batch/{batch_id}",
            headers={"Authorization": f"Bearer {MINERU_API_TOKEN}"},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json().get("data", {})
        results = data.get("extract_result", [])

        if not results:
            logger.warning("批次 %s：暂无结果", batch_id)
            time.sleep(POLL_INTERVAL_MINERU)
            continue

        terminal = {"done", "failed"}
        counts = {}
        for r in results:
            state = r.get("state", "unknown")
            counts[state] = counts.get(state, 0) + 1

        logger.info("批次 %s 状态：%s", batch_id, counts)

        if expected_keys_set is not None:
            terminal_keys = {
                r.get("data_id")
                for r in results
                if r.get("state") in terminal
                and r.get("data_id") in expected_keys_set
            }
            if expected_keys_set.issubset(terminal_keys):
                return results

        elif expected_count is not None:
            terminal_count = sum(
                1 for r in results if r.get("state") in terminal
            )
            if terminal_count >= expected_count:
                return results

        if all(r.get("state") in terminal for r in results):
            return results

        time.sleep(POLL_INTERVAL_MINERU)


def download_markdown(results):
    """Download zip results and extract markdown content.

    Args:
        results: list of result dicts from poll_batch.

    Returns:
        (successes, failures) where:
            successes = {data_id: {"text": md_content, "file_name": original_name}}
            failures  = {data_id: error_message}
    """
    successes = {}
    failures = {}

    for r in results:
        data_id = r.get("data_id", r.get("file_name", "unknown"))
        file_name = r.get("file_name", "unknown")

        if r.get("state") == "failed":
            failures[data_id] = r.get("err_msg", "unknown error")
            logger.warning("解析失败：%s，错误=%s", file_name, failures[data_id])
            continue

        zip_url = r.get("full_zip_url")
        if not zip_url:
            failures[data_id] = "no zip URL in done result"
            logger.warning("结果缺少 zip 下载地址：%s", file_name)
            continue

        try:
            zip_resp = requests.get(zip_url, timeout=120)
            zip_resp.raise_for_status()
        except Exception as exc:
            failures[data_id] = f"zip download error: {exc}"
            logger.error("下载 zip 失败：%s，错误=%s", file_name, exc)
            continue

        md_text = _extract_md_from_zip(zip_resp.content)
        if md_text is not None:
            successes[data_id] = {"text": md_text, "file_name": file_name}
        else:
            failures[data_id] = "no .md file found in zip"
            logger.warning("zip 中未找到 .md：%s", file_name)

    return successes, failures


def _extract_md_from_zip(content_bytes):
    """Extract the first .md file content from a zip archive."""
    try:
        with zipfile.ZipFile(io.BytesIO(content_bytes)) as zf:
            for name in zf.namelist():
                if name.endswith(".md"):
                    return zf.read(name).decode("utf-8")
    except (zipfile.BadZipFile, Exception) as exc:
        logger.error("解压 zip 失败：%s", exc)
    return None


def process_files(file_map):
    """Upload files in batches, poll results, and download markdown.

    Args:
        file_map: {file_path: task_key}

    Returns:
        (all_successes, all_failures) aggregated across all batches.
            all_successes = {task_key: {"text": md, "file_name": name}}
            all_failures  = {task_key: error_msg}
    """
    items = list(file_map.items())
    all_successes = {}
    all_failures = {}

    for start in range(0, len(items), MINERU_BATCH_SIZE):
        batch = items[start : start + MINERU_BATCH_SIZE]
        batch_num = start // MINERU_BATCH_SIZE + 1
        total_batches = (len(items) + MINERU_BATCH_SIZE - 1) // MINERU_BATCH_SIZE

        logger.info(
            "批次 %d/%d：文件数 %d", batch_num, total_batches, len(batch)
        )

        try:
            batch_id, uploaded, upload_failed = upload_batch(batch)
        except Exception as exc:
            logger.error("批次 %d 初始化失败：%s", batch_num, exc)
            for path, key in batch:
                all_failures[key] = f"upload error: {exc}"
            continue

        for key, err in upload_failed:
            all_failures[key] = f"upload error: {err}"

        if not uploaded:
            logger.warning(
                "批次 %d：全部上传失败，跳过轮询", batch_num,
            )
            continue

        try:
            expected_keys = [key for _, key in uploaded]
            results = poll_batch(
                batch_id,
                expected_count=len(uploaded),
                expected_keys=expected_keys,
            )
            successes, failures = download_markdown(results)
        except Exception as exc:
            logger.error("批次 %d 轮询/下载失败：%s", batch_num, exc)
            for _, key in uploaded:
                all_failures[key] = f"poll/download error: {exc}"
            continue

        all_successes.update(successes)
        all_failures.update(failures)

        logger.info(
            "批次 %d 完成：成功 %d，失败 %d",
            batch_num,
            len(successes),
            len(failures),
        )

    return all_successes, all_failures
