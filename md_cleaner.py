"""Markdown post-processing module between MinerU output and Dify upload."""

import base64
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import logging
import os
import re

import requests

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Pre-compiled regex patterns
# ---------------------------------------------------------------------------
_RE_IMAGE_PLACEHOLDER = re.compile(r"!\[.*?\]\(.*?\)")
_RE_MD_IMAGE = re.compile(r"!\[(?P<alt>[^\]]*)\]\((?P<link>[^)]+)\)")
_RE_HTML_TAG = re.compile(r"<[^>]+>")
_RE_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")
_RE_BLANK_LINES = re.compile(r"\n{3,}")
_RE_PAGE_NUMBER = re.compile(r"^\s*\d{1,4}\s*$", re.MULTILINE)
_RE_FIG_ID = re.compile(r"\b(fig(?:ure)?\.?\s*\d+[a-z]?)\b", re.IGNORECASE)
_RE_NUMBER = re.compile(
    r"(?<![A-Za-z])[-+]?\d+(?:\.\d+)?(?:\s?(?:%|‰|eV|nm|mA|V|W|h|min|s|°C|K|mg|g|mL|L|µmol|mmol|mol))?"
)

# ---------------------------------------------------------------------------
# Individual cleaning rules
# ---------------------------------------------------------------------------


def _collapse_blank_lines(text):
    """Collapse 3+ blank lines into standard paragraph spacing."""
    return _RE_BLANK_LINES.sub("\n\n", text)


def _strip_html_tags(text):
    """Remove HTML tags while preserving text content."""
    marker_token = "__MD_SPLIT_MARKER__"
    protected = text.replace("<!--split-->", marker_token)
    protected = _RE_HTML_TAG.sub("", protected)
    return protected.replace(marker_token, "<!--split-->")


def _remove_control_chars(text):
    """Remove non-printable control characters except tabs/newlines."""
    return _RE_CONTROL_CHARS.sub("", text)


def _remove_image_placeholders(text):
    """Remove Markdown image placeholders ![alt](path) precisely."""
    if not text:
        return text

    cleaned = []
    i = 0
    n = len(text)

    while i < n:
        if text.startswith("![", i):
            end = _find_markdown_image_end(text, i)
            if end > i:
                i = end
                continue
        cleaned.append(text[i])
        i += 1

    # Fallback pass for malformed edge cases that still match the simple form.
    return _RE_IMAGE_PLACEHOLDER.sub("", "".join(cleaned))


def _find_markdown_image_end(text, start_idx):
    """Return end index (exclusive) if a valid markdown image starts at start_idx."""
    if not text.startswith("![", start_idx):
        return -1

    n = len(text)
    i = start_idx + 2

    # Parse alt text: ![ ... ]
    while i < n:
        ch = text[i]
        if ch == "\\" and i + 1 < n:
            i += 2
            continue
        if ch == "\n":
            return -1
        if ch == "]":
            break
        i += 1

    if i >= n or text[i] != "]":
        return -1

    i += 1
    while i < n and text[i] in (" ", "\t"):
        i += 1

    # Destination starts with '('
    if i >= n or text[i] != "(":
        return -1

    depth = 0
    while i < n:
        ch = text[i]
        if ch == "\\" and i + 1 < n:
            i += 2
            continue
        if ch == "\n":
            return -1
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                return i + 1
        i += 1

    return -1


def _remove_page_numbers(text):
    """Remove standalone numeric page-number lines."""
    return _RE_PAGE_NUMBER.sub("", text)


def _remove_watermark(text, patterns):
    """Remove watermark text by configured regex patterns."""
    for pat in patterns:
        pat = pat.strip()
        if not pat:
            continue
        try:
            text = re.sub(pat, "", text)
        except re.error as exc:
            logger.warning("Invalid watermark regex skipped '%s': %s", pat, exc)
    return text


# ---------------------------------------------------------------------------
# Image summary rewrite
# ---------------------------------------------------------------------------


def _rewrite_images_with_summaries(text, file_meta, cfg):
    """Insert indexable image summary blocks after Markdown image links."""
    image_cfg = cfg.get("image_summary", {})
    image_stats = {
        "enabled": bool(image_cfg.get("enabled", True)),
        "total_images": 0,
        "ai_attempted": 0,
        "ai_succeeded": 0,
        "ai_failed": 0,
        "fallback_used": 0,
    }
    if not image_cfg.get("enabled", True):
        return text, 0, image_stats

    lines = text.split("\n")
    if not lines:
        return text, 0, image_stats

    max_images = _safe_int(image_cfg.get("max_images_per_doc"), 50)
    max_images = max(0, max_images)
    if max_images == 0:
        return text, 0, image_stats

    summary_jobs = _collect_image_summary_jobs(
        lines=lines,
        file_meta=file_meta or {},
        cfg=cfg,
        max_images=max_images,
    )
    if not summary_jobs:
        return text, 0, image_stats

    image_stats["total_images"] = len(summary_jobs)
    job_results = _execute_image_summary_jobs(summary_jobs, cfg)

    jobs_by_line = {}
    for job in summary_jobs:
        jobs_by_line.setdefault(job["line_idx"], []).append(job["job_idx"])

    inserted = 0
    rewritten = []

    for idx, line in enumerate(lines):
        rewritten.append(line)

        for job_idx in jobs_by_line.get(idx, []):
            block, source = job_results.get(job_idx, ("", "fallback_only"))
            if not block:
                continue

            if source == "ai_success":
                image_stats["ai_attempted"] += 1
                image_stats["ai_succeeded"] += 1
            elif source == "ai_failed":
                image_stats["ai_attempted"] += 1
                image_stats["ai_failed"] += 1
                image_stats["fallback_used"] += 1
            else:
                image_stats["fallback_used"] += 1

            rewritten.append("")
            rewritten.append(block)
            rewritten.append("")
            inserted += 1

    return "\n".join(rewritten), inserted, image_stats


def _collect_image_summary_jobs(lines, file_meta, cfg, max_images):
    assets = file_meta.get("image_assets") or []
    asset_index = _build_asset_index(assets)
    jobs = []

    for idx, line in enumerate(lines):
        matches = list(_RE_MD_IMAGE.finditer(line))
        if not matches:
            continue

        if _already_has_image_summary(lines, idx):
            continue

        doc_context = _collect_document_context(lines, idx, cfg)
        for match in matches:
            if len(jobs) >= max_images:
                break

            raw_link = (match.group("link") or "").strip()
            asset = _resolve_asset_for_link(raw_link, asset_index)
            alt_text = (match.group("alt") or "").strip()
            caption_text, nearby_text = _collect_image_context(lines, idx, alt_text)
            fig_id = _detect_fig_id(
                alt_text=alt_text,
                caption_text=caption_text,
                nearby_text=nearby_text,
                raw_link=raw_link,
                serial=len(jobs) + 1,
            )

            jobs.append(
                {
                    "job_idx": len(jobs),
                    "line_idx": idx,
                    "fig_id": fig_id,
                    "caption_text": caption_text,
                    "nearby_text": nearby_text,
                    "doc_context": doc_context,
                    "asset": asset,
                }
            )

        if len(jobs) >= max_images:
            break

    return jobs


def _execute_image_summary_jobs(summary_jobs, cfg):
    if not summary_jobs:
        return {}

    concurrency = _resolve_image_summary_concurrency(cfg)
    if concurrency <= 1 or len(summary_jobs) <= 1:
        return {
            job["job_idx"]: _run_image_summary_job(job, cfg)
            for job in summary_jobs
        }

    max_workers = min(concurrency, len(summary_jobs))
    logger.info(
        "image summary parallel enabled: workers=%d, tasks=%d",
        max_workers,
        len(summary_jobs),
    )

    results = {}
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(_run_image_summary_job, job, cfg): job
            for job in summary_jobs
        }
        for future in as_completed(futures):
            job = futures[future]
            job_idx = job["job_idx"]
            try:
                results[job_idx] = future.result()
            except Exception as exc:
                logger.warning(
                    "image summary async task crashed for %s: %s",
                    job["fig_id"],
                    exc,
                )
                fallback = _build_fallback_summary_block(
                    job["fig_id"],
                    job["caption_text"],
                    job["nearby_text"],
                )
                results[job_idx] = (fallback, "fallback_only")

    return results


def _run_image_summary_job(job, cfg):
    try:
        return _build_image_summary_block(
            fig_id=job["fig_id"],
            caption_text=job["caption_text"],
            nearby_text=job["nearby_text"],
            doc_context=job["doc_context"],
            asset=job["asset"],
            cfg=cfg,
        )
    except Exception as exc:
        logger.warning("image summary build failed for %s: %s", job["fig_id"], exc)
        fallback = _build_fallback_summary_block(
            job["fig_id"],
            job["caption_text"],
            job["nearby_text"],
        )
        return fallback, "fallback_only"


def _resolve_image_summary_concurrency(cfg):
    image_cfg = cfg.get("image_summary", {})
    value = _safe_int(image_cfg.get("concurrency"), 4)
    return max(1, min(32, value))


def _build_asset_index(assets):
    by_link = {}
    by_name = {}

    for asset in assets:
        link_path = _normalize_image_link(asset.get("link_path", ""))
        zip_path = _normalize_image_link(asset.get("zip_path", ""))
        saved_path = asset.get("saved_path", "")
        file_name = (asset.get("file_name") or os.path.basename(saved_path or "")).strip().lower()

        if link_path:
            by_link[link_path] = asset
        if zip_path and zip_path not in by_link:
            by_link[zip_path] = asset
        if file_name and file_name not in by_name:
            by_name[file_name] = asset

    return {"by_link": by_link, "by_name": by_name}


def _normalize_image_link(link):
    value = (link or "").strip()
    if not value:
        return ""

    value = value.strip("<>")
    if " " in value and not value.lower().startswith(("http://", "https://", "data:")):
        value = value.split(" ", 1)[0]

    value = value.split("?", 1)[0].split("#", 1)[0]
    value = value.replace("\\", "/")

    while value.startswith("./"):
        value = value[2:]

    return value


def _resolve_asset_for_link(raw_link, asset_index):
    norm = _normalize_image_link(raw_link)
    if not norm:
        return None

    by_link = asset_index.get("by_link", {})
    by_name = asset_index.get("by_name", {})

    if norm in by_link:
        return by_link[norm]

    file_name = os.path.basename(norm).strip().lower()
    if file_name and file_name in by_name:
        return by_name[file_name]

    return None


def _already_has_image_summary(lines, image_line_idx):
    upper = min(len(lines), image_line_idx + 12)
    for idx in range(image_line_idx + 1, upper):
        probe = lines[idx].strip()
        if not probe:
            continue
        if probe.startswith("- fig_id:"):
            return True
        if "provenance_location=" in probe or "provenance_evidence=" in probe:
            return True
        if _RE_MD_IMAGE.search(probe):
            break
    return False


def _collect_image_context(lines, image_line_idx, alt_text):
    caption_parts = []
    if alt_text:
        caption_parts.append(alt_text)

    prev_line = _nearest_nonempty_line(lines, image_line_idx, step=-1)
    next_line = _nearest_nonempty_line(lines, image_line_idx, step=1)

    if prev_line and _looks_like_caption_line(prev_line):
        caption_parts.append(prev_line)
    if next_line and _looks_like_caption_line(next_line):
        caption_parts.append(next_line)

    nearby = []
    start = max(0, image_line_idx - 6)
    end = min(len(lines), image_line_idx + 7)
    for idx in range(start, end):
        if idx == image_line_idx:
            continue
        line = lines[idx].strip()
        if not line or line == "<!--split-->":
            continue
        if _RE_MD_IMAGE.search(line):
            continue
        nearby.append(line)

    caption_text = " ".join(dict.fromkeys([p.strip() for p in caption_parts if p.strip()]))
    nearby_text = "\n".join(nearby)
    return caption_text, nearby_text


def _collect_document_context(lines, image_line_idx, cfg):
    image_cfg = cfg.get("image_summary", {})
    max_ctx = max(500, _safe_int(image_cfg.get("max_context_chars"), 3000))
    half_window = 50
    start = max(0, image_line_idx - half_window)
    end = min(len(lines), image_line_idx + half_window + 1)

    chunks = []
    for idx in range(start, end):
        line = lines[idx].strip()
        if not line:
            continue
        if line == "<!--split-->":
            continue
        chunks.append(line)

    context = "\n".join(chunks)
    if len(context) > max_ctx:
        context = context[:max_ctx]
    return context


def _nearest_nonempty_line(lines, base_idx, step):
    idx = base_idx + step
    while 0 <= idx < len(lines):
        probe = lines[idx].strip()
        if probe:
            return probe
        idx += step
    return ""


def _looks_like_caption_line(line):
    lowered = line.strip().lower()
    return (
        lowered.startswith("fig")
        or lowered.startswith("figure")
        or lowered.startswith("图")
        or "fig." in lowered
        or "figure" in lowered
    )


def _detect_fig_id(alt_text, caption_text, nearby_text, raw_link, serial):
    for source in (caption_text, nearby_text, alt_text, raw_link):
        matched = _RE_FIG_ID.search(source or "")
        if matched:
            return matched.group(1).replace("Figure", "fig").replace("FIGURE", "fig")

    file_stem = os.path.splitext(os.path.basename(_normalize_image_link(raw_link)))[0].strip()
    if file_stem:
        return file_stem

    return f"fig_{serial}"


def _build_image_summary_block(fig_id, caption_text, nearby_text, doc_context, asset, cfg):
    llm_block = None
    ai_attempted = _can_call_vision(asset, cfg)
    if ai_attempted:
        llm_block = _call_vision_summary(
            fig_id=fig_id,
            caption_text=caption_text,
            nearby_text=nearby_text,
            doc_context=doc_context,
            image_path=asset.get("saved_path"),
            cfg=cfg,
        )

    if llm_block:
        normalized = _normalize_llm_block(llm_block, fig_id)
        if normalized:
            return normalized, "ai_success"

    fallback = _build_fallback_summary_block(fig_id, caption_text, nearby_text)
    if ai_attempted:
        return fallback, "ai_failed"
    return fallback, "fallback_only"


def _can_call_vision(asset, cfg):
    if not asset:
        return False
    image_path = asset.get("saved_path")
    if not image_path or not os.path.exists(image_path):
        return False

    image_cfg = cfg.get("image_summary", {})
    if not image_cfg.get("enabled", True):
        return False

    api_key = str(image_cfg.get("api_key", "") or "").strip()
    model = str(image_cfg.get("model", "") or "").strip()
    return bool(api_key and model)


def _call_vision_summary(fig_id, caption_text, nearby_text, doc_context, image_path, cfg):
    image_cfg = cfg.get("image_summary", {})

    api_key = str(image_cfg.get("api_key", "") or "").strip()
    if not api_key:
        return None

    model = str(image_cfg.get("model", "") or "").strip()
    if not model:
        return None

    if not image_path or not os.path.exists(image_path):
        return None

    provider = _resolve_vision_provider(image_cfg.get("provider"))
    default_base_url = "https://api.openai.com/v1"
    base_url = str(image_cfg.get("api_base_url", default_base_url) or "").strip()
    if not base_url:
        base_url = default_base_url
    endpoints = _build_vision_endpoints(base_url)
    if provider == "newapi" and "openai.com" in base_url:
        logger.warning(
            "image_summary.provider=newapi but api_base_url=%s. "
            "请配置为你的 New API 服务地址（通常是 .../v1）。",
            base_url,
        )

    timeout_s = max(10, _safe_int(image_cfg.get("request_timeout_s"), 120))
    max_tokens = max(256, _safe_int(image_cfg.get("max_tokens"), 900))
    temperature = _safe_float(image_cfg.get("temperature"), 0.1)

    prompt = _build_vision_prompt(fig_id, caption_text, nearby_text, doc_context, cfg)

    try:
        with open(image_path, "rb") as f:
            image_bytes = f.read()

        b64 = base64.b64encode(image_bytes).decode("ascii")
        mime = _guess_image_mime(image_path)
        data_uri = f"data:{mime};base64,{b64}"

        payload = _build_vision_payload(
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            prompt=prompt,
            data_uri=data_uri,
            provider=provider,
            image_cfg=image_cfg,
        )
        use_system_proxy = _safe_bool(image_cfg.get("use_system_proxy"), True)
        session = requests.Session()
        session.trust_env = use_system_proxy

        last_exc = None
        try:
            for endpoint in endpoints:
                try:
                    resp = session.post(
                        endpoint,
                        headers={
                            "Authorization": f"Bearer {api_key}",
                            "Content-Type": "application/json",
                        },
                        json=payload,
                        timeout=timeout_s,
                    )
                    resp.raise_for_status()

                    body = _parse_json_response(resp)
                    choices = body.get("choices") or []
                    if not choices:
                        return None

                    message = choices[0].get("message") or {}
                    content = message.get("content", "")
                    if isinstance(content, list):
                        parts = []
                        for part in content:
                            if isinstance(part, dict) and part.get("type") == "text":
                                parts.append(part.get("text", ""))
                        content = "\n".join([p for p in parts if p])

                    if not isinstance(content, str):
                        return None

                    return content.strip()
                except Exception as exc:
                    last_exc = exc
                    logger.debug("vision endpoint failed for %s at %s: %s", fig_id, endpoint, exc)
        finally:
            session.close()

        raise RuntimeError(f"all vision endpoints failed, last_error={last_exc}")
    except Exception as exc:
        logger.warning("vision summary request failed for %s: %s", fig_id, exc)
        return None


def _resolve_vision_provider(raw_provider):
    provider = str(raw_provider or "openai").strip().lower()
    if provider in {"openai", "newapi"}:
        return provider
    return "openai"


def _build_vision_payload(model, temperature, max_tokens, prompt, data_uri, provider, image_cfg):
    payload = {
        "model": model,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "messages": [
            {
                "role": "system",
                "content": "You summarize scientific figures conservatively and must not invent values.",
            },
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": data_uri}},
                ],
            },
        ],
    }
    if provider == "newapi":
        payload["stream"] = False

    extra_body = _parse_extra_body_json(image_cfg.get("extra_body_json", ""))
    if extra_body:
        payload.update(extra_body)
    return payload


def _parse_extra_body_json(raw_text):
    text = str(raw_text or "").strip()
    if not text:
        return {}

    try:
        data = json.loads(text)
    except ValueError as exc:
        logger.warning("image_summary.extra_body_json 不是合法 JSON，已忽略：%s", exc)
        return {}

    if not isinstance(data, dict):
        logger.warning("image_summary.extra_body_json 必须是 JSON 对象，已忽略。")
        return {}
    return data


def _build_vision_endpoints(base_url):
    base = (base_url or "").strip().rstrip("/")
    if not base:
        base = "https://api.openai.com/v1"

    if base.endswith("/chat/completions"):
        candidates = [base]
    elif re.search(r"/v\d+$", base):
        candidates = [f"{base}/chat/completions"]
    else:
        candidates = [f"{base}/v1/chat/completions", f"{base}/chat/completions"]

    # Preserve order while deduplicating
    seen = set()
    ordered = []
    for ep in candidates:
        if ep in seen:
            continue
        seen.add(ep)
        ordered.append(ep)
    return ordered


def check_vision_connection(cfg):
    """Verify vision model API is reachable and API key is valid.

    Returns:
        dict: {"connected": bool, "message": str}
    """
    image_cfg = cfg.get("image_summary", {})

    if not _safe_bool(image_cfg.get("enabled"), True):
        return {"connected": False, "message": "图摘要回写未启用"}

    api_key = str(image_cfg.get("api_key") or "").strip()
    if not api_key:
        return {"connected": False, "message": "API Key 未配置"}
    if re.fullmatch(r"\*{4,}.{4}", api_key):
        return {"connected": False, "message": "API Key 显示为掩码值，请重新输入"}

    model = str(image_cfg.get("model") or "").strip()
    if not model:
        return {"connected": False, "message": "模型名称未配置"}

    base_url = str(image_cfg.get("api_base_url") or "https://api.openai.com/v1").strip()
    use_system_proxy = _safe_bool(image_cfg.get("use_system_proxy"), True)

    # Build /models endpoint from base_url
    base = base_url.rstrip("/")
    if base.endswith("/chat/completions"):
        base = base[: -len("/chat/completions")]
    if re.search(r"/v\d+$", base):
        models_url = f"{base}/models"
    else:
        models_url = f"{base}/v1/models"

    try:
        session = requests.Session()
        session.trust_env = use_system_proxy
        try:
            resp = session.get(
                models_url,
                headers={"Authorization": f"Bearer {api_key}"},
                timeout=10,
            )
        finally:
            session.close()

        if resp.status_code == 401:
            return {"connected": False, "message": "API Key 无效 (HTTP 401)"}
        if resp.status_code == 403:
            return {"connected": False, "message": "API Key 权限不足 (HTTP 403)"}
        if resp.status_code == 404:
            return _check_vision_via_chat(image_cfg, api_key, model, base_url, use_system_proxy)
        if resp.status_code >= 400:
            return {"connected": False, "message": f"服务异常 (HTTP {resp.status_code})"}
        return {"connected": True, "message": f"视觉模型服务连通 (model={model})"}
    except requests.Timeout:
        return {"connected": False, "message": "连接超时 (10s)"}
    except requests.ConnectionError:
        return {"connected": False, "message": "网络连接失败"}
    except requests.RequestException as exc:
        return {"connected": False, "message": f"请求异常: {exc}"}


def _check_vision_via_chat(image_cfg, api_key, model, base_url, use_system_proxy):
    """Fallback: verify connectivity via a minimal chat completion (text-only, 1 token)."""
    provider = _resolve_vision_provider(image_cfg.get("provider"))
    endpoints = _build_vision_endpoints(base_url)

    payload = {"model": model, "max_tokens": 1, "messages": [{"role": "user", "content": "hi"}]}
    if provider == "newapi":
        payload["stream"] = False

    extra_body = _parse_extra_body_json(image_cfg.get("extra_body_json", ""))
    if extra_body:
        payload.update(extra_body)

    session = requests.Session()
    session.trust_env = use_system_proxy
    last_exc = None
    try:
        for endpoint in endpoints:
            try:
                resp = session.post(
                    endpoint,
                    headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                    json=payload,
                    timeout=15,
                )
                if resp.status_code == 401:
                    return {"connected": False, "message": "API Key 无效 (HTTP 401)"}
                if resp.status_code == 403:
                    return {"connected": False, "message": "API Key 权限不足 (HTTP 403)"}
                if resp.status_code >= 500:
                    last_exc = RuntimeError(f"服务端错误 (HTTP {resp.status_code})")
                    continue
                return {"connected": True, "message": f"视觉模型服务连通 (model={model})"}
            except requests.RequestException as exc:
                last_exc = exc
    finally:
        session.close()

    msg = f"所有端点均不可达: {last_exc}" if last_exc else "无可用端点"
    return {"connected": False, "message": msg}


def _parse_json_response(resp):
    content_type = str(resp.headers.get("content-type", "") or "").lower()
    body_text = resp.text or ""
    body_head = body_text[:180].replace("\n", "\\n")

    if "application/json" not in content_type:
        raise RuntimeError(
            f"non-JSON response (status={resp.status_code}, content_type={content_type}, body_head={body_head})"
        )

    try:
        return resp.json()
    except ValueError as exc:
        raise RuntimeError(
            f"invalid JSON response (status={resp.status_code}, body_head={body_head})"
        ) from exc


def _guess_image_mime(path):
    ext = os.path.splitext(path or "")[1].lower()
    if ext in {".jpg", ".jpeg"}:
        return "image/jpeg"
    if ext == ".webp":
        return "image/webp"
    if ext == ".gif":
        return "image/gif"
    if ext in {".tif", ".tiff"}:
        return "image/tiff"
    if ext == ".bmp":
        return "image/bmp"
    return "image/png"


def _build_vision_prompt(fig_id, caption_text, nearby_text, doc_context, cfg):
    image_cfg = cfg.get("image_summary", {})
    max_ctx = max(500, _safe_int(image_cfg.get("max_context_chars"), 3000))

    caption = (caption_text or "").strip() or "未提及"
    nearby = (nearby_text or "").strip() or "未提及"
    doc_ctx = (doc_context or "").strip() or "未提及"
    if len(nearby) > max_ctx:
        nearby = nearby[:max_ctx]
    if len(doc_ctx) > max_ctx:
        doc_ctx = doc_ctx[:max_ctx]

    language = _infer_language(caption + "\n" + nearby)
    language_rule = "中文" if language == "zh" else "English"

    return (
        "请基于输入文本与图片内容生成可索引图摘要回写块。\n"
        "必须遵守：\n"
        "1) 不能从图片中猜测具体曲线点位；仅允许使用输入文本中明确给出的数字。\n"
        "2) 若只有趋势且无明确数字，输出 value_type=trend_only。\n"
        "3) 核心结论必须用英文一句话。\n"
        "4) 除核心结论外，输出语言尽量与输入正文一致（本次建议：%s）。\n"
        "5) 只输出 Markdown 块，不要解释。\n\n"
        "输入：\n"
        "fig_id: %s\n"
        "caption_text:\n%s\n\n"
        "nearby_discussion:\n%s\n"
        "\nfull_parsed_text_context:\n%s\n"
    ) % (language_rule, fig_id, caption, nearby, doc_ctx)


def _normalize_llm_block(block_text, fig_id):
    cleaned = (block_text or "").strip()
    if not cleaned:
        return ""

    cleaned = re.sub(r"^```(?:markdown)?\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```$", "", cleaned).strip()

    lower = cleaned.lower()
    if "- fig_id:" not in lower:
        cleaned = f"- fig_id: {fig_id}\n" + cleaned

    if "<!--split-->" not in cleaned:
        cleaned = f"<!--split-->\n{cleaned}\n<!--split-->"

    return cleaned


def _build_fallback_summary_block(fig_id, caption_text, nearby_text):
    source = "\n".join([caption_text or "", nearby_text or ""]).strip()
    lang = _infer_language(source)

    evidence_sentences = _extract_supporting_sentences(source, max_sentences=3)
    evidence = " || ".join(evidence_sentences) if evidence_sentences else "未提及"

    numbers = _RE_NUMBER.findall(source)
    numbers = [n.strip() for n in numbers if n.strip()]
    number_text = ", ".join(numbers[:8]) if numbers else "趋势：文中仅描述趋势，未给出明确数值"

    samples = _extract_sample_tokens(source)
    metrics = _extract_metrics(source)
    conditions = _extract_conditions(source)
    comparison = _extract_comparison(source)
    core_conclusion = _core_conclusion_en(source)

    if lang == "zh":
        lines = [
            "<!--split-->",
            f"- fig_id: {fig_id}",
            f"- 核心结论: {core_conclusion}",
            f"- 涉及样品: {samples or '未提及'}",
            f"- 涉及指标: {metrics or '未提及'}",
            f"- 关键条件: {conditions or '未提及'}",
            f"- 关键数值: {number_text}",
            f"- 对比关系: {comparison or '未提及'}",
            "- provenance_location=fig_id caption/Results section",
            f"- provenance_evidence=\"{evidence}\"",
        ]
    else:
        lines = [
            "<!--split-->",
            f"- fig_id: {fig_id}",
            f"- core_conclusion: {core_conclusion}",
            f"- samples: {samples or 'not mentioned'}",
            f"- metrics: {metrics or 'not mentioned'}",
            f"- key_conditions: {conditions or 'not mentioned'}",
            f"- key_numbers: {number_text if numbers else 'trend only'}",
            f"- comparison: {comparison or 'not mentioned'}",
            "- provenance_location=fig_id caption/Results section",
            f"- provenance_evidence=\"{evidence}\"",
        ]

    if not numbers:
        lines.append("- value_type=trend_only")

    lines.append("<!--split-->")
    return "\n".join(lines)


def _extract_supporting_sentences(text, max_sentences=3):
    if not text:
        return []

    raw_parts = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        raw_parts.extend(re.split(r"(?<=[。！？!?;；\.])\s+", line))

    seen = set()
    picked = []
    for part in raw_parts:
        sentence = part.strip()
        if not sentence or sentence in seen:
            continue
        seen.add(sentence)
        if len(sentence) < 6:
            continue
        picked.append(sentence)
        if len(picked) >= max_sentences:
            break

    return picked


def _infer_language(text):
    if not text:
        return "zh"

    cjk_count = len(re.findall(r"[\u4e00-\u9fff]", text))
    ratio = cjk_count / max(1, len(text))
    return "zh" if ratio >= 0.02 else "en"


def _extract_sample_tokens(text):
    if not text:
        return ""

    tokens = re.findall(r"\b[A-Z][A-Za-z0-9_\-]{1,24}\b", text)
    blocked = {
        "Fig", "Figure", "Results", "Discussion", "Supplementary", "UV", "Vis", "XRD", "SEM", "TEM",
    }

    uniq = []
    for token in tokens:
        if token in blocked:
            continue
        if token not in uniq:
            uniq.append(token)
        if len(uniq) >= 6:
            break

    return ", ".join(uniq)


def _extract_metrics(text):
    if not text:
        return ""

    metrics = []
    mapping = [
        ("h2", "H2 rate"),
        ("aqy", "AQY"),
        ("stability", "stability"),
        ("band", "band structure/gap"),
        ("hydrogen", "hydrogen production"),
        ("photocurrent", "photocurrent"),
        ("selectivity", "selectivity"),
        ("conversion", "conversion"),
    ]

    lowered = text.lower()
    for needle, label in mapping:
        if needle in lowered and label not in metrics:
            metrics.append(label)

    return ", ".join(metrics)


def _extract_conditions(text):
    if not text:
        return ""

    clues = []
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    for line in lines:
        lowered = line.lower()
        if (
            "lambda" in lowered
            or "λ" in line
            or "nm" in lowered
            or "sacrificial" in lowered
            or "catalyst" in lowered
            or "dosage" in lowered
            or "pH" in line
            or "illumination" in lowered
            or "light" in lowered
        ):
            clues.append(line)
            if len(clues) >= 2:
                break

    return " || ".join(clues)


def _extract_comparison(text):
    if not text:
        return ""

    rules = [
        r"[^.。！？!?]*(higher than|lower than|better than|worse than|more stable than)[^.。！？!?]*",
        r"[^.。！？!?]*(优于|高于|低于|更稳定|最高|最低)[^.。！？!?]*",
    ]

    for pattern in rules:
        matched = re.search(pattern, text, flags=re.IGNORECASE)
        if matched:
            return matched.group(0).strip()

    return ""


def _core_conclusion_en(text):
    if not text:
        return "The figure summarizes the key trend discussed in the manuscript text."

    lowered = text.lower()
    if any(term in lowered for term in ["higher than", "better than", "improved", "increase", "enhanced"]):
        return "The figure indicates improved performance for the leading sample under the reported conditions."
    if any(term in lowered for term in ["lower than", "decrease", "decline", "drop"]):
        return "The figure shows a declining trend for the reported metric compared with the reference condition."

    return "The figure captures a comparative trend that is described in the surrounding manuscript text."


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

_MIN_CLEANED_LENGTH = 10


def clean_markdown(text, cfg, file_meta=None):
    """Clean one markdown document."""
    md_cfg = cfg["md_clean"]
    stats = {
        "original_len": len(text),
        "cleaned_len": len(text),
        "rules_applied": [],
        "image_summary": {
            "enabled": bool(cfg.get("image_summary", {}).get("enabled", True)),
            "total_images": 0,
            "ai_attempted": 0,
            "ai_succeeded": 0,
            "ai_failed": 0,
            "fallback_used": 0,
        },
    }

    if not md_cfg.get("enabled", True):
        return text, stats

    if not text:
        return "", stats

    original_text = text

    text, summary_count, image_stats = _rewrite_images_with_summaries(text, file_meta or {}, cfg)
    stats["image_summary"] = image_stats
    if summary_count > 0:
        stats["rules_applied"].append(f"rewrite_image_summaries({summary_count})")

    if md_cfg.get("remove_image_placeholders", True):
        text = _remove_image_placeholders(text)
        stats["rules_applied"].append("remove_image_placeholders")

    if md_cfg.get("strip_html", True):
        text = _strip_html_tags(text)
        stats["rules_applied"].append("strip_html")

    if md_cfg.get("remove_control_chars", True):
        text = _remove_control_chars(text)
        stats["rules_applied"].append("remove_control_chars")

    if md_cfg.get("remove_page_numbers", False):
        text = _remove_page_numbers(text)
        stats["rules_applied"].append("remove_page_numbers")

    if md_cfg.get("remove_watermark", False) and md_cfg.get("watermark_patterns", ""):
        patterns = md_cfg["watermark_patterns"].split(",")
        text = _remove_watermark(text, patterns)
        stats["rules_applied"].append("remove_watermark")

    if md_cfg.get("collapse_blank_lines", True):
        text = _collapse_blank_lines(text)
        stats["rules_applied"].append("collapse_blank_lines")

    cleaned = text.strip()

    if len(cleaned) < _MIN_CLEANED_LENGTH and len(original_text) >= _MIN_CLEANED_LENGTH:
        logger.warning(
            "Cleaned markdown is too short (%d chars), fallback to original (%d chars)",
            len(cleaned),
            len(original_text),
        )
        cleaned = original_text
        stats["rules_applied"].append("fallback_to_original")

    stats["cleaned_len"] = len(cleaned)
    return cleaned, stats


def clean_all(md_results, cfg):
    """Clean all markdown results."""
    md_cfg = cfg["md_clean"]
    image_cfg = cfg.get("image_summary", {})

    if not md_cfg.get("enabled", True):
        total_chars = sum(len(v.get("text", "")) for v in md_results.values())
        agg = {
            "total_original": total_chars,
            "total_cleaned": total_chars,
            "reduction_pct": 0.0,
            "file_count": len(md_results),
            "image_summary": {
                "enabled": bool(image_cfg.get("enabled", True)),
                "total_images": 0,
                "ai_attempted": 0,
                "ai_succeeded": 0,
                "ai_failed": 0,
                "fallback_used": 0,
            },
        }
        return md_results, agg

    total_original = 0
    total_cleaned = 0
    image_totals = {
        "enabled": bool(image_cfg.get("enabled", True)),
        "total_images": 0,
        "ai_attempted": 0,
        "ai_succeeded": 0,
        "ai_failed": 0,
        "fallback_used": 0,
    }
    cleaned_results = {}

    for key, data in md_results.items():
        original_text = data.get("text", "")
        try:
            cleaned_text, file_stats = clean_markdown(original_text, cfg, file_meta=data)
        except Exception as exc:
            logger.warning("Markdown clean failed for '%s', keep original: %s", data.get("file_name", key), exc)
            cleaned_text = original_text
            file_stats = {
                "original_len": len(original_text),
                "cleaned_len": len(original_text),
                "image_summary": {
                    "enabled": bool(image_cfg.get("enabled", True)),
                    "total_images": 0,
                    "ai_attempted": 0,
                    "ai_succeeded": 0,
                    "ai_failed": 0,
                    "fallback_used": 0,
                },
            }

        total_original += file_stats["original_len"]
        total_cleaned += file_stats["cleaned_len"]
        file_image_stats = file_stats.get("image_summary") or {}
        image_totals["total_images"] += _safe_int(file_image_stats.get("total_images"), 0)
        image_totals["ai_attempted"] += _safe_int(file_image_stats.get("ai_attempted"), 0)
        image_totals["ai_succeeded"] += _safe_int(file_image_stats.get("ai_succeeded"), 0)
        image_totals["ai_failed"] += _safe_int(file_image_stats.get("ai_failed"), 0)
        image_totals["fallback_used"] += _safe_int(file_image_stats.get("fallback_used"), 0)

        cleaned_results[key] = {**data, "text": cleaned_text}

    reduction_pct = 0.0
    if total_original > 0:
        reduction_pct = (1 - total_cleaned / total_original) * 100

    agg = {
        "total_original": total_original,
        "total_cleaned": total_cleaned,
        "reduction_pct": reduction_pct,
        "file_count": len(md_results),
        "image_summary": image_totals,
    }
    return cleaned_results, agg


def _safe_int(value, default_value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(default_value)


def _safe_float(value, default_value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default_value)


def _safe_bool(value, default_value):
    if value is None:
        return bool(default_value)
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in ("true", "1", "yes", "on")
