import json
import logging
import os
from collections import deque

import requests

logger = logging.getLogger(__name__)

SUPPORTED_FORMATS = {".pdf", ".doc", ".docx", ".ppt", ".pptx", ".png", ".jpg", ".jpeg"}

MAX_PAGES_GUARD = 500  # 防止分页死循环


def _mcp_call(method, mcp_url, params=None):
    """Send a JSON-RPC call to the Zotero MCP server."""
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": method,
    }
    if params is not None:
        payload["params"] = params

    resp = requests.post(mcp_url, json=payload, timeout=30)
    resp.raise_for_status()
    body = resp.json()

    if "error" in body:
        raise RuntimeError(f"MCP error: {body['error']}")

    return body.get("result", {})


def _parse_mcp_content(result):
    """Extract parsed JSON from MCP content wrapper.

    MCP responses follow the pattern:
        {"content": [{"type": "text", "text": "<json-string>"}]}
    The inner JSON may be a direct value or wrapped as {"data": ...}.
    """
    content = result.get("content", [])
    if not isinstance(content, list) or len(content) == 0:
        return result

    first = content[0]
    if not isinstance(first, dict) or "text" not in first:
        return result

    try:
        parsed = json.loads(first["text"])
    except (json.JSONDecodeError, TypeError):
        return result

    if isinstance(parsed, dict) and "data" in parsed:
        return parsed["data"]
    return parsed


def check_connection(cfg):
    """Verify the Zotero MCP server is reachable."""
    mcp_url = cfg["zotero"]["mcp_url"]
    try:
        resp = requests.post(
            mcp_url,
            json={"jsonrpc": "2.0", "id": 0, "method": "tools/list"},
            timeout=5,
        )
        resp.raise_for_status()
        body = resp.json()
        return "error" not in body
    except (requests.RequestException, ValueError):
        return False


def _extract_list_payload(data, candidate_keys=("results", "items", "collections", "subcollections")):
    """Extract a list from MCP response data, trying multiple known keys."""
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in candidate_keys:
            val = data.get(key)
            if isinstance(val, list):
                return val
    return []


def list_collections(cfg, mode="standard", page_size=100):
    """Fetch all collections from Zotero, handling pagination."""
    mcp_url = cfg["zotero"]["mcp_url"]
    all_collections = []
    offset = 0
    page_size = max(1, page_size)
    for _ in range(MAX_PAGES_GUARD):
        result = _mcp_call(
            "tools/call",
            mcp_url,
            {"name": "get_collections", "arguments": {"mode": mode, "limit": page_size, "offset": offset}},
        )
        data = _parse_mcp_content(result)
        items = _extract_list_payload(data)
        if not items:
            break
        all_collections.extend(items)
        if len(items) < page_size:
            break
        offset += page_size
    else:
        logger.warning("list_collections 命中分页保护上限（%d 页），结果可能不完整", MAX_PAGES_GUARD)
    return all_collections


def get_subcollections_list(mcp_url, collection_key, page_size=100):
    """Fetch direct subcollections of a given collection."""
    all_subs = []
    offset = 0
    page_size = max(1, page_size)
    for _ in range(MAX_PAGES_GUARD):
        result = _mcp_call(
            "tools/call",
            mcp_url,
            {"name": "get_subcollections", "arguments": {"collectionKey": collection_key, "limit": page_size, "offset": offset}},
        )
        data = _parse_mcp_content(result)
        items = _extract_list_payload(data)
        if not items:
            break
        all_subs.extend(items)
        if len(items) < page_size:
            break
        offset += page_size
    else:
        logger.warning("get_subcollections_list(%s) 命中分页保护上限，结果可能不完整", collection_key)
    return all_subs


def expand_collection_scope(mcp_url, collection_keys, recursive=True):
    """Expand collection keys to include all descendant collections via BFS.

    Returns deduplicated list of collection keys.
    """
    effective = set(collection_keys)
    if not recursive:
        return list(effective)

    queue = deque(collection_keys)
    while queue:
        current = queue.popleft()
        try:
            subs = get_subcollections_list(mcp_url, current)
        except Exception as exc:
            logger.warning("获取子分组失败：%s，错误=%s", current, exc)
            continue
        for sub in subs:
            sub_key = sub.get("key", "") if isinstance(sub, dict) else str(sub)
            if sub_key and sub_key not in effective:
                effective.add(sub_key)
                queue.append(sub_key)
    return list(effective)


def iter_collection_items(mcp_url, collection_key, page_size=50):
    """Paginate through all items in a collection."""
    all_items = []
    offset = 0
    page_size = max(1, page_size)
    for _ in range(MAX_PAGES_GUARD):
        result = _mcp_call(
            "tools/call",
            mcp_url,
            {"name": "get_collection_items", "arguments": {"collectionKey": collection_key, "limit": page_size, "offset": offset}},
        )
        data = _parse_mcp_content(result)
        items = _extract_list_payload(data)
        if not items:
            break
        all_items.extend(items)
        if len(items) < page_size:
            break
        offset += page_size
    else:
        logger.warning("iter_collection_items(%s) 命中分页保护上限，结果可能不完整", collection_key)
    return all_items


def collect_items_by_collections(mcp_url, collection_keys, recursive=True, page_size=50):
    """Collect deduplicated items from one or more collections.

    Returns list of item dicts, deduplicated by item key.
    """
    effective_keys = expand_collection_scope(mcp_url, collection_keys, recursive=recursive)
    logger.info(
        "分组展开：输入 %d 个，展开后 %d 个（recursive=%s）",
        len(collection_keys), len(effective_keys), recursive,
    )

    seen_item_keys = set()
    all_items = []
    for coll_key in effective_keys:
        try:
            items = iter_collection_items(mcp_url, coll_key, page_size=page_size)
        except Exception as exc:
            logger.warning("获取分组条目失败：%s，错误=%s", coll_key, exc)
            continue
        for item in items:
            item_key = item.get("key", "") if isinstance(item, dict) else str(item)
            if item_key and item_key not in seen_item_keys:
                seen_item_keys.add(item_key)
                all_items.append(item)

    logger.info("从 %d 个分组收集到 %d 个去重条目", len(effective_keys), len(all_items))
    return all_items


def search_all_items(mcp_url, page_size=50):
    """Paginate through search_library to collect every item key."""
    all_items = []
    offset = 0
    page_size = max(1, page_size)

    for _ in range(MAX_PAGES_GUARD):
        result = _mcp_call(
            "tools/call",
            mcp_url,
            {
                "name": "search_library",
                "arguments": {"q": "", "limit": page_size, "offset": offset},
            },
        )

        data = _parse_mcp_content(result)

        if isinstance(data, dict):
            items = data.get("results", data.get("items", []))
        elif isinstance(data, list):
            items = data
        else:
            break

        if not isinstance(items, list) or len(items) == 0:
            break

        all_items.extend(items)
        if len(items) < page_size:
            break
        offset += page_size
    else:
        logger.warning("search_all_items 命中分页保护上限（%d 页），结果可能不完整", MAX_PAGES_GUARD)

    logger.info("已从 Zotero 获取 %d 条条目", len(all_items))
    return all_items


def get_attachment_paths(mcp_url, item_key):
    """Return local file paths for supported attachments of a given item."""
    result = _mcp_call(
        "tools/call",
        mcp_url,
        {"name": "get_item_details", "arguments": {"itemKey": item_key}},
    )

    details = _parse_mcp_content(result)

    attachments = details.get("attachments", []) if isinstance(details, dict) else []
    if not attachments:
        logger.warning(
            "条目 %s 没有附件。响应字段：%s",
            item_key,
            list(details.keys()) if isinstance(details, dict) else type(details).__name__,
        )
    paths = []

    for att in attachments:
        file_path = att.get("filePath") or att.get("path") or ""
        if not file_path:
            logger.warning("条目 %s 的附件缺少 filePath/path。字段：%s", item_key, list(att.keys()))
            continue

        ext = os.path.splitext(file_path)[1].lower()
        if ext not in SUPPORTED_FORMATS:
            logger.warning("跳过不支持格式（%s）：%s", ext, file_path)
            continue

        if not os.path.isfile(file_path):
            logger.warning("磁盘文件不存在：%s", file_path)
            continue

        paths.append(file_path)

    return paths


def collect_files(
    cfg,
    uploaded_item_keys=None,
    collection_keys=None,
    recursive=True,
    page_size=50,
):
    """Collect all valid attachment paths, deduplicated and filtered.

    Args:
        cfg: configuration dict with cfg["zotero"]["mcp_url"].
        uploaded_item_keys: set of Zotero item base keys already present in Dify.
        collection_keys: list of collection keys to filter by, or None for all.
        recursive: whether to include subcollection items (default True).
        page_size: pagination size for item queries.

    Returns:
        dict: {file_path: task_key} where task_key = "item_key#index"
    """
    mcp_url = cfg["zotero"]["mcp_url"]

    if uploaded_item_keys is None:
        uploaded_item_keys = set()

    if collection_keys:
        items = collect_items_by_collections(mcp_url, collection_keys, recursive=recursive, page_size=page_size)
    else:
        items = search_all_items(mcp_url, page_size=page_size)
    file_map = {}
    seen_paths = set()
    skipped_processed = 0

    for item in items:
        item_key = item.get("key", "") if isinstance(item, dict) else str(item)
        if not item_key:
            logger.warning("跳过 key 为空的条目")
            continue

        if item_key in uploaded_item_keys:
            skipped_processed += 1
            continue

        try:
            paths = get_attachment_paths(mcp_url, item_key)
        except Exception as exc:
            logger.warning("获取条目附件失败：%s，错误=%s", item_key, exc)
            continue

        paths = sorted(paths)

        for idx, p in enumerate(paths):
            task_key = f"{item_key}#{idx}"
            if p not in seen_paths:
                seen_paths.add(p)
                file_map[p] = task_key

    logger.info(
        "共收集到 %d 个文件（已处理跳过 %d 个）",
        len(file_map),
        skipped_processed,
    )
    return file_map
