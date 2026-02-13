import json
import logging
import os
import re
import time
from pathlib import Path

import requests
try:
    import yaml
except Exception:  # pragma: no cover - fallback for missing dependency
    yaml = None

from config import (
    DIFY_API_KEY,
    DIFY_BASE_URL,
    DIFY_CHUNK_OVERLAP,
    DIFY_DATASET_NAME,
    DIFY_DOC_FORM,
    DIFY_DOC_LANGUAGE,
    DIFY_PARENT_MODE,
    DIFY_PIPELINE_FILE,
    DIFY_PROCESS_MODE,
    DIFY_REMOVE_EXTRA_SPACES,
    DIFY_REMOVE_URLS_EMAILS,
    DIFY_SEGMENT_MAX_TOKENS,
    DIFY_SEGMENT_SEPARATOR,
    DIFY_SUBCHUNK_MAX_TOKENS,
    DIFY_SUBCHUNK_OVERLAP,
    DIFY_SUBCHUNK_SEPARATOR,
    DIFY_UPLOAD_DELAY,
    POLL_INTERVAL_DIFY,
)

logger = logging.getLogger(__name__)

TEXT_MODEL_FORM = "text_model"
HIERARCHICAL_FORM = "hierarchical_model"
RAG_PIPELINE_MODE = "rag_pipeline"
_SHARED_REF_PATTERN = re.compile(r"\{\{#rag\.shared\.([A-Za-z0-9_]+)#\}\}")
_PIPELINE_RULE_CACHE = None


def _headers(content_type="application/json"):
    headers = {"Authorization": f"Bearer {DIFY_API_KEY}"}
    if content_type:
        headers["Content-Type"] = content_type
    return headers


def _parse_int(value):
    try:
        if value is None or value == "":
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _parse_bool(value):
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"1", "true", "yes", "on"}:
            return True
        if lowered in {"0", "false", "no", "off"}:
            return False
    return None


def _discover_pipeline_file():
    configured = (DIFY_PIPELINE_FILE or "").strip()
    candidates = []
    if configured:
        configured_path = Path(configured)
        if configured_path.is_file():
            return configured_path
        logger.warning("未找到 DIFY_PIPELINE_FILE 指定的文件: %s", configured)

    base_names = []
    if DIFY_DATASET_NAME:
        base_names.append(DIFY_DATASET_NAME.strip())

    search_dirs = [
        Path.cwd(),
        Path(__file__).resolve().parent,
        Path.home() / "Downloads",
    ]

    for base in base_names:
        if not base:
            continue
        for suffix in ("", " (1)", " (2)"):
            filename = f"{base}{suffix}.pipeline"
            for d in search_dirs:
                candidates.append(d / filename)

    seen = set()
    deduped = []
    for p in candidates:
        key = str(p)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(p)

    existing = [p for p in deduped if p.is_file()]
    if not existing:
        return None

    # 自动发现时优先使用最新导出的 pipeline 文件。
    existing.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return existing[0]


def _resolve_param_value(param_entry, shared_defaults):
    if not isinstance(param_entry, dict):
        return param_entry

    value = param_entry.get("value")
    if isinstance(value, str):
        matched = _SHARED_REF_PATTERN.fullmatch(value.strip())
        if matched:
            return shared_defaults.get(matched.group(1))
    return value


def _extract_pipeline_rule_overrides(pipeline_obj):
    workflow = (pipeline_obj or {}).get("workflow") or {}
    graph = workflow.get("graph") or {}
    nodes = graph.get("nodes") or []
    rag_vars = workflow.get("rag_pipeline_variables") or []

    shared_defaults = {}
    for item in rag_vars:
        if not isinstance(item, dict):
            continue
        var_name = (item.get("variable") or "").strip()
        if not var_name:
            continue
        shared_defaults[var_name] = item.get("default_value")

    parentchild_params = {}
    for node in nodes:
        data = node.get("data") if isinstance(node, dict) else None
        if not isinstance(data, dict):
            continue
        if data.get("tool_name") != "parentchild_chunker":
            continue
        parentchild_params = data.get("tool_parameters") or {}
        break

    extracted = {}
    if parentchild_params:
        resolved_parent_mode = _resolve_param_value(parentchild_params.get("parent_mode"), shared_defaults)
        if resolved_parent_mode not in (None, ""):
            extracted["parent_mode"] = str(resolved_parent_mode)

        resolved_parent_sep = _resolve_param_value(parentchild_params.get("separator"), shared_defaults)
        if resolved_parent_sep not in (None, ""):
            extracted["segmentation_separator"] = str(resolved_parent_sep)

        resolved_parent_len = _parse_int(_resolve_param_value(parentchild_params.get("max_length"), shared_defaults))
        if resolved_parent_len is not None:
            extracted["segmentation_max_tokens"] = resolved_parent_len

        resolved_child_sep = _resolve_param_value(parentchild_params.get("subchunk_separator"), shared_defaults)
        if resolved_child_sep not in (None, ""):
            extracted["subchunk_separator"] = str(resolved_child_sep)

        resolved_child_len = _parse_int(_resolve_param_value(parentchild_params.get("subchunk_max_length"), shared_defaults))
        if resolved_child_len is not None:
            extracted["subchunk_max_tokens"] = resolved_child_len

        resolved_clean1 = _parse_bool(_resolve_param_value(parentchild_params.get("remove_extra_spaces"), shared_defaults))
        if resolved_clean1 is not None:
            extracted["remove_extra_spaces"] = resolved_clean1

        resolved_clean2 = _parse_bool(_resolve_param_value(parentchild_params.get("remove_urls_emails"), shared_defaults))
        if resolved_clean2 is not None:
            extracted["remove_urls_emails"] = resolved_clean2

    fallback_map = {
        "parent_mode": "parent_mode",
        "segmentation_separator": "parent_dilmiter",
        "segmentation_max_tokens": "parent_length",
        "subchunk_separator": "child_delimiter",
        "subchunk_max_tokens": "child_length",
        "remove_extra_spaces": "clean_1",
        "remove_urls_emails": "clean_2",
    }
    for target_key, shared_key in fallback_map.items():
        if target_key in extracted:
            continue
        raw = shared_defaults.get(shared_key)
        if raw in (None, ""):
            continue
        if target_key in {"segmentation_max_tokens", "subchunk_max_tokens"}:
            parsed = _parse_int(raw)
            if parsed is not None:
                extracted[target_key] = parsed
            continue
        if target_key in {"remove_extra_spaces", "remove_urls_emails"}:
            parsed = _parse_bool(raw)
            if parsed is not None:
                extracted[target_key] = parsed
            continue
        extracted[target_key] = str(raw)

    return extracted


def _load_pipeline_rule_overrides():
    global _PIPELINE_RULE_CACHE
    if _PIPELINE_RULE_CACHE is not None:
        return _PIPELINE_RULE_CACHE

    _PIPELINE_RULE_CACHE = {}
    if yaml is None:
        logger.warning("未安装 PyYAML，无法解析 .pipeline 文件，将回退到 .env 参数。")
        return _PIPELINE_RULE_CACHE

    pipeline_path = _discover_pipeline_file()
    if not pipeline_path:
        return _PIPELINE_RULE_CACHE

    try:
        with open(pipeline_path, "r", encoding="utf-8") as f:
            pipeline_obj = yaml.safe_load(f) or {}
        overrides = _extract_pipeline_rule_overrides(pipeline_obj)
        if not isinstance(overrides, dict):
            overrides = {}
        _PIPELINE_RULE_CACHE = overrides

        if overrides:
            logger.info(
                "已从 pipeline 文件加载分块参数: %s",
                pipeline_path,
            )
        else:
            logger.warning(
                "pipeline 文件已找到但未解析到 parentchild_chunker 参数，将回退到 .env: %s",
                pipeline_path,
            )
    except Exception as exc:
        logger.warning("读取 pipeline 文件失败，将回退到 .env（%s）: %s", pipeline_path, exc)

    return _PIPELINE_RULE_CACHE


def _list_datasets():
    datasets = []
    page = 1
    while True:
        resp = requests.get(
            f"{DIFY_BASE_URL}/datasets",
            headers=_headers(content_type=None),
            params={"page": page, "limit": 100},
            timeout=30,
        )
        resp.raise_for_status()
        body = resp.json()
        datasets.extend(body.get("data", []))
        if not body.get("has_more", False):
            break
        page += 1
    return datasets


def _fetch_dataset_detail(dataset_id):
    resp = requests.get(
        f"{DIFY_BASE_URL}/datasets/{dataset_id}",
        headers=_headers(content_type=None),
        timeout=30,
    )
    resp.raise_for_status()
    body = resp.json()
    if isinstance(body, dict) and isinstance(body.get("data"), dict):
        return body["data"]
    return body if isinstance(body, dict) else {}


def get_dataset_info(dataset_id):
    """读取知识库详情（doc_form/runtime_mode/name）。"""
    try:
        body = _fetch_dataset_detail(dataset_id)
        return {
            "id": dataset_id,
            "name": (body.get("name") or "").strip(),
            "doc_form": (body.get("doc_form") or "").strip(),
            "runtime_mode": (body.get("runtime_mode") or "").strip(),
            "indexing_technique": (body.get("indexing_technique") or "").strip(),
        }
    except Exception as exc:
        logger.warning("读取知识库详情失败（%s）：%s", dataset_id, exc)
        return {
            "id": dataset_id,
            "name": "",
            "doc_form": "",
            "runtime_mode": "",
            "indexing_technique": "",
        }


def get_dataset_doc_form(dataset_id):
    """兼容旧接口：仅返回 doc_form。"""
    return get_dataset_info(dataset_id).get("doc_form", "")


def get_or_create_dataset():
    """严格使用配置中的知识库名，不会自动创建新知识库。"""
    datasets = _list_datasets()
    for ds in datasets:
        if ds.get("name") == DIFY_DATASET_NAME:
            logger.info("使用配置知识库: %s (%s)", DIFY_DATASET_NAME, ds["id"])
            return ds["id"]

    raise RuntimeError(
        f"未找到配置知识库 DIFY_DATASET_NAME={DIFY_DATASET_NAME}。"
        "按你的配置，程序不会自动新建知识库，请先在 Dify 创建后再运行。"
    )


def _build_process_rule(resolved_doc_form=""):
    """按配置构建 process_rule。"""
    mode = (DIFY_PROCESS_MODE or "").strip().lower()
    if mode == "automatic":
        return {"mode": "automatic"}
    if mode != "custom":
        logger.warning("DIFY_PROCESS_MODE=%r 非法，回退为 custom", DIFY_PROCESS_MODE)

    pipeline_overrides = _load_pipeline_rule_overrides()
    remove_extra_spaces = pipeline_overrides.get("remove_extra_spaces", DIFY_REMOVE_EXTRA_SPACES)
    remove_urls_emails = pipeline_overrides.get("remove_urls_emails", DIFY_REMOVE_URLS_EMAILS)
    segmentation_separator = pipeline_overrides.get("segmentation_separator", DIFY_SEGMENT_SEPARATOR)
    segmentation_max_tokens = pipeline_overrides.get("segmentation_max_tokens", DIFY_SEGMENT_MAX_TOKENS)
    parent_mode = pipeline_overrides.get("parent_mode", DIFY_PARENT_MODE)
    subchunk_separator = pipeline_overrides.get("subchunk_separator", DIFY_SUBCHUNK_SEPARATOR)
    subchunk_max_tokens = pipeline_overrides.get("subchunk_max_tokens", DIFY_SUBCHUNK_MAX_TOKENS)

    rules = {
        "pre_processing_rules": [
            {"id": "remove_extra_spaces", "enabled": remove_extra_spaces},
            {"id": "remove_urls_emails", "enabled": remove_urls_emails},
        ],
        "segmentation": {
            "separator": segmentation_separator,
            "max_tokens": segmentation_max_tokens,
            "chunk_overlap": DIFY_CHUNK_OVERLAP,
        },
    }

    # hierarchical_model 需要显式提供父子分块规则，否则会出现 completed 但 0 分块。
    if (resolved_doc_form or "").strip() == HIERARCHICAL_FORM:
        rules["parent_mode"] = parent_mode
        rules["subchunk_segmentation"] = {
            "separator": subchunk_separator,
            "max_tokens": subchunk_max_tokens,
            "chunk_overlap": DIFY_SUBCHUNK_OVERLAP,
        }

    return {
        "mode": "custom",
        "rules": rules,
    }


def _to_markdown_doc_name(item_key, file_name):
    base_name = os.path.splitext(file_name or "document")[0].strip() or "document"
    return f"[{item_key}] {base_name}.md"


def _upload_by_text(dataset_id, doc_name, text, resolved_doc_form):
    body = {
        "name": doc_name,
        "text": text,
        "indexing_technique": "high_quality",
        "process_rule": _build_process_rule(resolved_doc_form),
    }
    if resolved_doc_form:
        body["doc_form"] = resolved_doc_form
    if DIFY_DOC_LANGUAGE:
        body["doc_language"] = DIFY_DOC_LANGUAGE

    resp = requests.post(
        f"{DIFY_BASE_URL}/datasets/{dataset_id}/document/create-by-text",
        headers=_headers(),
        json=body,
        timeout=60,
    )
    resp.raise_for_status()
    return resp.json().get("batch", "")


def _upload_markdown_as_file(
    dataset_id,
    doc_name,
    text,
    resolved_doc_form,
    runtime_mode="",
):
    payload = {
        "indexing_technique": "high_quality",
        "process_rule": _build_process_rule(resolved_doc_form),
    }
    if resolved_doc_form:
        payload["doc_form"] = resolved_doc_form
    if DIFY_DOC_LANGUAGE:
        payload["doc_language"] = DIFY_DOC_LANGUAGE

    files = {"file": (doc_name, text.encode("utf-8"), "text/markdown")}
    data = {"data": json.dumps(payload, ensure_ascii=False)}

    resp = requests.post(
        f"{DIFY_BASE_URL}/datasets/{dataset_id}/document/create-by-file",
        headers=_headers(content_type=None),
        files=files,
        data=data,
        timeout=120,
    )
    resp.raise_for_status()
    return resp.json().get("batch", "")


def upload_document(dataset_id, item_key, file_name, md_text, doc_form="", runtime_mode=""):
    """上传单个 Markdown 文本到 Dify。"""
    text = md_text if isinstance(md_text, str) else str(md_text or "")
    if not text.strip():
        logger.error("Markdown 为空，跳过上传: [%s] %s", item_key, file_name)
        return None

    doc_name = _to_markdown_doc_name(item_key, file_name)
    resolved_doc_form = (doc_form or "").strip() or (DIFY_DOC_FORM or "").strip()
    if not resolved_doc_form:
        resolved_doc_form = TEXT_MODEL_FORM

    try:
        use_text_upload = resolved_doc_form == TEXT_MODEL_FORM and (runtime_mode or "").strip() != RAG_PIPELINE_MODE
        if use_text_upload:
            batch = _upload_by_text(dataset_id, doc_name, text, resolved_doc_form)
        else:
            if (runtime_mode or "").strip() == RAG_PIPELINE_MODE:
                logger.info("当前知识库 runtime_mode=rag_pipeline，将以 Markdown 文件方式上传。")
            else:
                logger.warning(
                    "当前知识库 doc_form=%s，改用 create-by-file 上传 Markdown。",
                    resolved_doc_form,
                )
            batch = _upload_markdown_as_file(
                dataset_id=dataset_id,
                doc_name=doc_name,
                text=text,
                resolved_doc_form=resolved_doc_form,
                runtime_mode=runtime_mode,
            )
        logger.info("已上传到 Dify: %s (batch=%s)", doc_name, batch)
        return batch
    except requests.HTTPError as exc:
        if exc.response is not None:
            logger.error(
                "Dify 上传失败 %s: status=%s, response=%s",
                doc_name,
                exc.response.status_code,
                exc.response.text,
            )
        else:
            logger.error("Dify 上传失败 %s: %s", doc_name, exc)
        return None
    except Exception as exc:
        logger.error("Dify 上传失败 %s: %s", doc_name, exc)
        return None


def wait_for_indexing(dataset_id, batch, max_wait=600):
    """轮询 Dify 索引状态，直到完成/失败/超时。"""
    if not batch:
        return False

    start = time.time()
    while time.time() - start < max_wait:
        try:
            resp = requests.get(
                f"{DIFY_BASE_URL}/datasets/{dataset_id}/documents/{batch}/indexing-status",
                headers=_headers(content_type=None),
                timeout=30,
            )
            resp.raise_for_status()
            docs = resp.json().get("data", [])
            if not docs:
                time.sleep(POLL_INTERVAL_DIFY)
                continue

            if any(d.get("indexing_status") == "error" for d in docs):
                logger.error("索引失败，batch=%s", batch)
                return False

            if all(d.get("indexing_status") == "completed" for d in docs):
                total_segments = sum(int(d.get("total_segments") or 0) for d in docs)
                if total_segments <= 0:
                    logger.error("索引完成但分块数为 0，batch=%s", batch)
                    return False
                return True

        except Exception as exc:
            logger.warning("查询索引状态失败: %s", exc)

        time.sleep(POLL_INTERVAL_DIFY)

    logger.warning("索引超时，batch=%s", batch)
    return False


def upload_all(dataset_id, md_results, dataset_info=None):
    """上传全部 Markdown 文本到 Dify。"""
    uploaded = []
    failed = []
    pending_batches = {}

    info = dataset_info or get_dataset_info(dataset_id)
    dataset_doc_form = info.get("doc_form", "")
    dataset_runtime_mode = info.get("runtime_mode", "")
    configured_doc_form = (DIFY_DOC_FORM or "").strip()
    effective_doc_form = dataset_doc_form or configured_doc_form or TEXT_MODEL_FORM

    if dataset_doc_form and configured_doc_form and dataset_doc_form != configured_doc_form:
        logger.warning(
            "配置 DIFY_DOC_FORM=%s 与知识库 doc_form=%s 不一致，已自动使用知识库值。",
            configured_doc_form,
            dataset_doc_form,
        )

    if effective_doc_form == HIERARCHICAL_FORM:
        logger.warning(
            "当前知识库 doc_form=hierarchical_model。将继续上传 Markdown，并由索引结果判定成功/失败。"
        )

    for item_key, data in md_results.items():
        batch = upload_document(
            dataset_id=dataset_id,
            item_key=item_key,
            file_name=data["file_name"],
            md_text=data["text"],
            doc_form=effective_doc_form,
            runtime_mode=dataset_runtime_mode,
        )
        if batch:
            pending_batches[item_key] = batch
        else:
            failed.append(item_key)
        time.sleep(DIFY_UPLOAD_DELAY)

    logger.info("Dify submit: %d 接受, %d 拒绝", len(pending_batches), len(failed))
    logger.info("等待 %d 个批次完成索引...", len(pending_batches))

    for item_key, batch in pending_batches.items():
        if wait_for_indexing(dataset_id, batch):
            uploaded.append(item_key)
        else:
            failed.append(item_key)
            logger.error("索引失败：条目 %s, 批次=%s", item_key, batch)

    return uploaded, failed
