"""Markdown 清洗模块 -- MinerU OCR 输出 -> Dify 上传之间的后处理管道。"""

import logging
import re

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Pre-compiled regex patterns
# ---------------------------------------------------------------------------
_RE_IMAGE_PLACEHOLDER = re.compile(r"!\[.*?\]\(.*?\)")
_RE_HTML_TAG = re.compile(r"<[^>]+>")
_RE_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")
_RE_BLANK_LINES = re.compile(r"\n{3,}")
_RE_PAGE_NUMBER = re.compile(r"^\s*\d{1,4}\s*$", re.MULTILINE)


# ---------------------------------------------------------------------------
# Individual cleaning rules
# ---------------------------------------------------------------------------

def _collapse_blank_lines(text):
    """将 3 个及以上连续空行压缩为 2 个（标准段落间隔）。"""
    return _RE_BLANK_LINES.sub("\n\n", text)


def _strip_html_tags(text):
    """移除残留 HTML 标签，保留标签内文本。"""
    return _RE_HTML_TAG.sub("", text)


def _remove_control_chars(text):
    """清除不可见控制字符（保留 \\t、\\n、\\r）。"""
    return _RE_CONTROL_CHARS.sub("", text)


def _remove_image_placeholders(text):
    """移除 Markdown 图片占位符 ![alt](path)。"""
    return _RE_IMAGE_PLACEHOLDER.sub("", text)


def _remove_page_numbers(text):
    """移除独立行的页码数字（1-4 位纯数字）。"""
    return _RE_PAGE_NUMBER.sub("", text)


def _remove_watermark(text, patterns):
    """按配置的正则模式列表逐一移除水印文本。"""
    for pat in patterns:
        pat = pat.strip()
        if not pat:
            continue
        try:
            text = re.sub(pat, "", text)
        except re.error as exc:
            logger.warning("水印正则无效，已跳过 '%s': %s", pat, exc)
    return text


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

_MIN_CLEANED_LENGTH = 10


def clean_markdown(text, cfg):
    """清洗单篇 Markdown 文本。

    Args:
        text: 原始 Markdown 文本。
        cfg: 配置字典，从 cfg["md_clean"] 读取清洗开关。

    Returns:
        tuple[str, dict]: (cleaned_text, stats)
            stats 包含 original_len、cleaned_len、rules_applied 列表。
    """
    md_cfg = cfg["md_clean"]
    stats = {"original_len": len(text), "cleaned_len": len(text), "rules_applied": []}

    if not md_cfg.get("enabled", True):
        return text, stats

    if not text:
        return "", stats

    original_text = text

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
            "清洗后文本过短（%d 字符），回退为原始文本（%d 字符）",
            len(cleaned),
            len(original_text),
        )
        cleaned = original_text
        stats["rules_applied"].append("fallback_to_original")

    stats["cleaned_len"] = len(cleaned)
    return cleaned, stats


def clean_all(md_results, cfg):
    """批量清洗 md_results 字典。

    Args:
        md_results: {key: {"text": str, "file_name": str, ...}}
        cfg: 配置字典，从 cfg["md_clean"] 读取清洗开关。

    Returns:
        tuple[dict, dict]: (cleaned_results, aggregate_stats)
            aggregate_stats 包含 total_original、total_cleaned、reduction_pct、file_count。
    """
    md_cfg = cfg["md_clean"]

    if not md_cfg.get("enabled", True):
        total_chars = sum(len(v.get("text", "")) for v in md_results.values())
        agg = {
            "total_original": total_chars,
            "total_cleaned": total_chars,
            "reduction_pct": 0.0,
            "file_count": len(md_results),
        }
        return md_results, agg

    total_original = 0
    total_cleaned = 0
    cleaned_results = {}

    for key, data in md_results.items():
        original_text = data.get("text", "")
        try:
            cleaned_text, file_stats = clean_markdown(original_text, cfg)
        except Exception as exc:
            logger.warning("清洗文件 '%s' 时出错，保留原文: %s", data.get("file_name", key), exc)
            cleaned_text = original_text
            file_stats = {"original_len": len(original_text), "cleaned_len": len(original_text)}

        total_original += file_stats["original_len"]
        total_cleaned += file_stats["cleaned_len"]

        cleaned_results[key] = {**data, "text": cleaned_text}

    reduction_pct = 0.0
    if total_original > 0:
        reduction_pct = (1 - total_cleaned / total_original) * 100

    agg = {
        "total_original": total_original,
        "total_cleaned": total_cleaned,
        "reduction_pct": reduction_pct,
        "file_count": len(md_results),
    }
    return cleaned_results, agg
