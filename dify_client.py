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

logger = logging.getLogger(__name__)

TEXT_MODEL_FORM = "text_model"
HIERARCHICAL_FORM = "hierarchical_model"
RAG_PIPELINE_MODE = "rag_pipeline"
_SHARED_REF_PATTERN = re.compile(r"\{\{#rag\.shared\.([A-Za-z0-9_]+)#\}\}")
_DOC_NAME_ITEM_KEY_PATTERN = re.compile(r"^\[([^\]]+)\]\s")

POLL_INTERVAL_DIFY = 10


def _headers(api_key, content_type="application/json"):
    headers = {"Authorization": f"Bearer {api_key}"}
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


def _discover_pipeline_file(pipeline_file, dataset_name):
    configured = (pipeline_file or "").strip()
    candidates = []
    if configured:
        configured_path = Path(configured)
        if configured_path.is_file():
            return configured_path
        logger.warning("未找到 DIFY_PIPELINE_FILE 指定的文件: %s", configured)

    base_names = []
    if dataset_name:
        base_names.append(dataset_name.strip())

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


def _load_pipeline_rule_overrides(cfg):
    """加载 pipeline 文件覆盖参数（每次调用重新发现，不使用全局缓存）。"""
    dify_cfg = cfg.get("dify", {})

    if yaml is None:
        logger.warning("未安装 PyYAML，无法解析 .pipeline 文件，将回退到配置参数。")
        return {}

    pipeline_path = _discover_pipeline_file(
        dify_cfg.get("pipeline_file", ""),
        dify_cfg.get("dataset_name", ""),
    )
    if not pipeline_path:
        return {}

    try:
        with open(pipeline_path, "r", encoding="utf-8") as f:
            pipeline_obj = yaml.safe_load(f) or {}
        overrides = _extract_pipeline_rule_overrides(pipeline_obj)
        if not isinstance(overrides, dict):
            overrides = {}

        if overrides:
            logger.info("已从 pipeline 文件加载分块参数: %s", pipeline_path)
        else:
            logger.warning(
                "pipeline 文件已找到但未解析到 parentchild_chunker 参数，将回退到配置: %s",
                pipeline_path,
            )
    except Exception as exc:
        logger.warning("读取 pipeline 文件失败，将回退到配置（%s）: %s", pipeline_path, exc)
        overrides = {}

    return overrides


def _list_datasets(base_url, api_key):
    datasets = []
    page = 1
    while True:
        resp = requests.get(
            f"{base_url}/datasets",
            headers=_headers(api_key, content_type=None),
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


def _fetch_dataset_detail(base_url, api_key, dataset_id):
    resp = requests.get(
        f"{base_url}/datasets/{dataset_id}",
        headers=_headers(api_key, content_type=None),
        timeout=30,
    )
    resp.raise_for_status()
    body = resp.json()
    if isinstance(body, dict) and isinstance(body.get("data"), dict):
        return body["data"]
    return body if isinstance(body, dict) else {}


def get_dataset_info(cfg, dataset_id):
    """读取知识库详情（doc_form/runtime_mode/name）。"""
    dify_cfg = cfg.get("dify", {})
    base_url = dify_cfg.get("base_url", "")
    api_key = dify_cfg.get("api_key", "")
    try:
        body = _fetch_dataset_detail(base_url, api_key, dataset_id)
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


def get_dataset_document_total(cfg, dataset_id):
    """读取知识库文档总数。失败时返回 None。"""
    dify_cfg = cfg.get("dify", {})
    base_url = dify_cfg.get("base_url", "")
    api_key = dify_cfg.get("api_key", "")
    try:
        resp = requests.get(
            f"{base_url}/datasets/{dataset_id}/documents",
            headers=_headers(api_key, content_type=None),
            params={"page": 1, "limit": 1},
            timeout=30,
        )
        resp.raise_for_status()
        body = resp.json()

        total = body.get("total")
        if isinstance(total, int):
            return total
        if isinstance(total, str) and total.isdigit():
            return int(total)

        data = body.get("data")
        has_more = body.get("has_more")
        if isinstance(data, list) and has_more is False and not data:
            return 0

        logger.warning("读取知识库文档总数返回格式异常（%s）：%s", dataset_id, body)
    except Exception as exc:
        logger.warning("读取知识库文档总数失败（%s）：%s", dataset_id, exc)
    return None


def get_dataset_document_name_index(cfg, dataset_id):
    """拉取知识库文档名索引。"""
    dify_cfg = cfg.get("dify", {})
    base_url = dify_cfg.get("base_url", "")
    api_key = dify_cfg.get("api_key", "")

    names = set()
    prefixed_item_keys = set()
    total = None
    page = 1

    try:
        while True:
            resp = requests.get(
                f"{base_url}/datasets/{dataset_id}/documents",
                headers=_headers(api_key, content_type=None),
                params={"page": page, "limit": 100},
                timeout=30,
            )
            resp.raise_for_status()
            body = resp.json()

            if total is None:
                total_value = body.get("total")
                if isinstance(total_value, int):
                    total = total_value
                elif isinstance(total_value, str) and total_value.isdigit():
                    total = int(total_value)

            docs = body.get("data")
            docs = docs if isinstance(docs, list) else []
            for doc in docs:
                if not isinstance(doc, dict):
                    continue
                name = (doc.get("name") or "").strip()
                if not name:
                    continue
                names.add(name)
                matched = _DOC_NAME_ITEM_KEY_PATTERN.match(name)
                if matched:
                    prefixed_item_keys.add(matched.group(1))

            if not body.get("has_more", False):
                break
            page += 1
    except Exception as exc:
        logger.warning("拉取知识库文档名索引失败（%s）：%s", dataset_id, exc)

    return {
        "total": total,
        "names": names,
        "prefixed_item_keys": prefixed_item_keys,
    }


def get_or_create_dataset(cfg):
    """严格使用配置中的知识库名，不会自动创建新知识库。"""
    dify_cfg = cfg.get("dify", {})
    base_url = dify_cfg.get("base_url", "")
    api_key = dify_cfg.get("api_key", "")
    dataset_name = dify_cfg.get("dataset_name", "")

    datasets = _list_datasets(base_url, api_key)
    for ds in datasets:
        if ds.get("name") == dataset_name:
            logger.info("使用配置知识库: %s (%s)", dataset_name, ds["id"])
            return ds["id"]

    raise RuntimeError(
        f"未找到配置知识库 dataset_name={dataset_name}。"
        "检查 dify 中的数据库是否与项目中的一致。"
    )


def _build_process_rule(cfg, resolved_doc_form=""):
    """按配置构建 process_rule。"""
    dify_cfg = cfg.get("dify", {})
    mode = (dify_cfg.get("process_mode") or "").strip().lower()
    if mode == "automatic":
        return {"mode": "automatic"}
    if mode != "custom":
        logger.warning("process_mode=%r 非法，回退为 custom", dify_cfg.get("process_mode"))

    pipeline_overrides = _load_pipeline_rule_overrides(cfg)
    remove_extra_spaces = pipeline_overrides.get("remove_extra_spaces", dify_cfg.get("remove_extra_spaces", True))
    remove_urls_emails = pipeline_overrides.get("remove_urls_emails", dify_cfg.get("remove_urls_emails", False))
    segmentation_separator = pipeline_overrides.get("segmentation_separator", dify_cfg.get("segment_separator", "\\n\\n"))
    segmentation_max_tokens = pipeline_overrides.get("segmentation_max_tokens", dify_cfg.get("segment_max_tokens", 800))
    parent_mode = pipeline_overrides.get("parent_mode", dify_cfg.get("parent_mode", "paragraph"))
    subchunk_separator = pipeline_overrides.get("subchunk_separator", dify_cfg.get("subchunk_separator", "\\n"))
    subchunk_max_tokens = pipeline_overrides.get("subchunk_max_tokens", dify_cfg.get("subchunk_max_tokens", 256))

    rules = {
        "pre_processing_rules": [
            {"id": "remove_extra_spaces", "enabled": remove_extra_spaces},
            {"id": "remove_urls_emails", "enabled": remove_urls_emails},
        ],
        "segmentation": {
            "separator": segmentation_separator,
            "max_tokens": segmentation_max_tokens,
            "chunk_overlap": dify_cfg.get("chunk_overlap", 0),
        },
    }

    if (resolved_doc_form or "").strip() == HIERARCHICAL_FORM:
        rules["parent_mode"] = parent_mode
        rules["subchunk_segmentation"] = {
            "separator": subchunk_separator,
            "max_tokens": subchunk_max_tokens,
            "chunk_overlap": dify_cfg.get("subchunk_overlap", 0),
        }

    return {
        "mode": "custom",
        "rules": rules,
    }


def build_markdown_doc_name(item_key, file_name):
    base_name = os.path.splitext(file_name or "document")[0].strip() or "document"
    return f"[{item_key}] {base_name}.md"


def _to_markdown_doc_name(item_key, file_name):
    return build_markdown_doc_name(item_key, file_name)


def _upload_by_text(cfg, dataset_id, doc_name, text, resolved_doc_form):
    dify_cfg = cfg.get("dify", {})
    base_url = dify_cfg.get("base_url", "")
    api_key = dify_cfg.get("api_key", "")
    doc_language = dify_cfg.get("doc_language", "")

    body = {
        "name": doc_name,
        "text": text,
        "indexing_technique": "high_quality",
        "process_rule": _build_process_rule(cfg, resolved_doc_form),
    }
    if resolved_doc_form:
        body["doc_form"] = resolved_doc_form
    if doc_language:
        body["doc_language"] = doc_language

    resp = requests.post(
        f"{base_url}/datasets/{dataset_id}/document/create-by-text",
        headers=_headers(api_key),
        json=body,
        timeout=60,
    )
    resp.raise_for_status()
    return resp.json().get("batch", "")


def _upload_markdown_as_file(
    cfg,
    dataset_id,
    doc_name,
    text,
    resolved_doc_form,
    runtime_mode="",
):
    dify_cfg = cfg.get("dify", {})
    base_url = dify_cfg.get("base_url", "")
    api_key = dify_cfg.get("api_key", "")
    doc_language = dify_cfg.get("doc_language", "")

    payload = {
        "indexing_technique": "high_quality",
        "process_rule": _build_process_rule(cfg, resolved_doc_form),
    }
    if resolved_doc_form:
        payload["doc_form"] = resolved_doc_form
    if doc_language:
        payload["doc_language"] = doc_language

    files = {"file": (doc_name, text.encode("utf-8"), "text/markdown")}
    data = {"data": json.dumps(payload, ensure_ascii=False)}

    resp = requests.post(
        f"{base_url}/datasets/{dataset_id}/document/create-by-file",
        headers=_headers(api_key, content_type=None),
        files=files,
        data=data,
        timeout=120,
    )
    resp.raise_for_status()
    return resp.json().get("batch", "")


def upload_document(cfg, dataset_id, item_key, file_name, md_text, doc_form="", runtime_mode=""):
    """上传单个 Markdown 文本到 Dify。"""
    dify_cfg = cfg.get("dify", {})
    text = md_text if isinstance(md_text, str) else str(md_text or "")
    if not text.strip():
        logger.error("Markdown 为空，跳过上传: [%s] %s", item_key, file_name)
        return None

    doc_name = _to_markdown_doc_name(item_key, file_name)
    resolved_doc_form = (doc_form or "").strip() or (dify_cfg.get("doc_form") or "").strip()
    if not resolved_doc_form:
        resolved_doc_form = TEXT_MODEL_FORM

    try:
        use_text_upload = resolved_doc_form == TEXT_MODEL_FORM and (runtime_mode or "").strip() != RAG_PIPELINE_MODE
        if use_text_upload:
            batch = _upload_by_text(cfg, dataset_id, doc_name, text, resolved_doc_form)
        else:
            if (runtime_mode or "").strip() == RAG_PIPELINE_MODE:
                logger.info("当前知识库 runtime_mode=rag_pipeline，将以 Markdown 文件方式上传。")
            else:
                logger.warning(
                    "当前知识库 doc_form=%s，改用 create-by-file 上传 Markdown。",
                    resolved_doc_form,
                )
            batch = _upload_markdown_as_file(
                cfg=cfg,
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


def wait_for_indexing(cfg, dataset_id, batch, max_wait=None):
    """轮询 Dify 索引状态，直到完成/失败/超时。"""
    dify_cfg = cfg.get("dify", {})
    base_url = dify_cfg.get("base_url", "")
    api_key = dify_cfg.get("api_key", "")
    index_max_wait = dify_cfg.get("index_max_wait_s", 1800)

    if not batch:
        return False

    if max_wait is None or max_wait <= 0:
        max_wait = index_max_wait

    def _fetch_docs():
        resp = requests.get(
            f"{base_url}/datasets/{dataset_id}/documents/{batch}/indexing-status",
            headers=_headers(api_key, content_type=None),
            timeout=30,
        )
        resp.raise_for_status()
        docs = resp.json().get("data", [])
        return docs if isinstance(docs, list) else []

    def _doc_error_text(doc):
        err = doc.get("error")
        if err in (None, "", {}, []):
            return ""
        if isinstance(err, str):
            return err.strip()
        return str(err).strip()

    def _validate_completed_docs(docs):
        for d in docs:
            doc_id = d.get("id", "unknown")
            err_text = _doc_error_text(d)
            if err_text:
                return False, f"doc={doc_id} error={err_text}"

            total_segments = int(d.get("total_segments") or 0)
            completed_segments = int(d.get("completed_segments") or 0)
            if total_segments <= 0:
                return False, f"doc={doc_id} total_segments={total_segments}"
            if completed_segments < total_segments:
                return (
                    False,
                    f"doc={doc_id} completed_segments={completed_segments} total_segments={total_segments}",
                )

        return True, ""

    start = time.time()
    while time.time() - start < max_wait:
        try:
            docs = _fetch_docs()
            if not docs:
                time.sleep(POLL_INTERVAL_DIFY)
                continue

            if any(d.get("indexing_status") == "error" for d in docs):
                logger.error("索引失败，batch=%s", batch)
                return False

            if all(d.get("indexing_status") == "completed" for d in docs):
                ok, reason = _validate_completed_docs(docs)
                if not ok:
                    logger.error("索引完成但存在异常，batch=%s，%s", batch, reason)
                    return False
                return True

        except Exception as exc:
            logger.warning("查询索引状态失败: %s", exc)

        time.sleep(POLL_INTERVAL_DIFY)

    logger.warning(
        "索引超时，batch=%s，已等待 %ss（可通过配置 index_max_wait_s 调整）",
        batch,
        max_wait,
    )

    try:
        docs = _fetch_docs()
        if docs and all(d.get("indexing_status") == "completed" for d in docs):
            ok, reason = _validate_completed_docs(docs)
            if ok:
                total_segments = sum(int(d.get("total_segments") or 0) for d in docs)
                logger.warning("超时后复查发现已完成，batch=%s，segments=%d", batch, total_segments)
                return True
            logger.error("索引超时后复查仍异常，batch=%s，%s", batch, reason)
    except Exception as exc:
        logger.warning("索引超时后复查失败: %s", exc)

    return False




def _emit_upload_progress(progress_callback, **payload):
    """Best-effort callback dispatch for upload/index progress events."""
    if progress_callback is None:
        return
    try:
        progress_callback(payload)
    except Exception as exc:
        logger.warning("upload progress callback failed: %s", exc)

def upload_all(cfg, dataset_id, md_results, dataset_info=None, progress_callback=None):
    """上传全部 Markdown 文本到 Dify。"""
    dify_cfg = cfg.get("dify", {})
    upload_delay = dify_cfg.get("upload_delay", 1)
    index_max_wait = dify_cfg.get("index_max_wait_s", 1800)
    configured_doc_form = (dify_cfg.get("doc_form") or "").strip()

    uploaded = []
    failed = []
    pending_batches = {}

    info = dataset_info or get_dataset_info(cfg, dataset_id)
    dataset_doc_form = info.get("doc_form", "")
    dataset_runtime_mode = info.get("runtime_mode", "")
    effective_doc_form = dataset_doc_form or configured_doc_form or TEXT_MODEL_FORM

    if dataset_doc_form and configured_doc_form and dataset_doc_form != configured_doc_form:
        logger.warning(
            "配置 doc_form=%s 与知识库 doc_form=%s 不一致，已自动使用知识库值。",
            configured_doc_form,
            dataset_doc_form,
        )

    if effective_doc_form == HIERARCHICAL_FORM:
        logger.warning(
            "当前知识库 doc_form=hierarchical_model。将继续上传 Markdown，并由索引结果判定成功/失败。"
        )

    for item_key, data in md_results.items():
        batch = upload_document(
            cfg=cfg,
            dataset_id=dataset_id,
            item_key=item_key,
            file_name=data["file_name"],
            md_text=data["text"],
            doc_form=effective_doc_form,
            runtime_mode=dataset_runtime_mode,
        )
        if batch:
            pending_batches[item_key] = batch
            _emit_upload_progress(
                progress_callback,
                phase="submit_ok",
                item_key=item_key,
                batch=batch,
                success=True,
                message=f"Dify submit accepted: {data['file_name']}",
            )
        else:
            failed.append(item_key)
            _emit_upload_progress(
                progress_callback,
                phase="submit_failed",
                item_key=item_key,
                batch="",
                success=False,
                message=f"Dify submit failed: {data['file_name']}",
            )
        time.sleep(upload_delay)

    logger.info("Dify submit: %d 接受, %d 拒绝", len(pending_batches), len(failed))
    logger.info(
        "等待 %d 个批次完成索引（单批最大等待 %ss）...",
        len(pending_batches),
        index_max_wait,
    )
    _emit_upload_progress(
        progress_callback,
        phase="index_wait_begin",
        item_key="",
        batch="",
        success=True,
        message=f"Waiting Dify indexing for {len(pending_batches)} file(s)",
    )

    for item_key, batch in pending_batches.items():
        if wait_for_indexing(cfg, dataset_id, batch):
            uploaded.append(item_key)
            _emit_upload_progress(
                progress_callback,
                phase="index_ok",
                item_key=item_key,
                batch=batch,
                success=True,
                message=f"Dify indexing completed: {item_key}",
            )
        else:
            failed.append(item_key)
            logger.error("dify indexing failed: item=%s, batch=%s", item_key, batch)
            _emit_upload_progress(
                progress_callback,
                phase="index_failed",
                item_key=item_key,
                batch=batch,
                success=False,
                message=f"Dify indexing failed: {item_key}",
            )

    return uploaded, failed
