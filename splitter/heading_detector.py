"""标题检测器 — Markdown 标题语法 + 正则模式匹配。"""

import re

from splitter.md_element_extractor import MDElement

# 默认中文标题正则（同 VerbaAurea）
_DEFAULT_HEADING_PATTERNS = [
    r"^第[一二三四五六七八九十百千]+[章节]",
    r"^[一二三四五六七八九十]+[、\.]",
    r"^\d+(\.\d+)*\s*[\u4e00-\u9fff]{0,30}$",
    r"^[\(（][一二三四五六七八九十]+[\)）]",
    r"^[\(（]?\d+[\)）]",
]

_SENTENCE_ENDS = ("。", "！", "？", ".", "!", "?", "；", ";")


def _compile_patterns(custom_regex_str: str = "") -> list[re.Pattern]:
    """编译标题匹配正则列表。"""
    patterns = list(_DEFAULT_HEADING_PATTERNS)
    if custom_regex_str:
        for part in custom_regex_str.split(","):
            part = part.strip()
            if part:
                patterns.append(part)
    compiled = []
    for p in patterns:
        try:
            compiled.append(re.compile(p))
        except re.error:
            pass
    return compiled


def _content_looks_like_heading(text: str, patterns: list[re.Pattern]) -> bool:
    """基于内容判断是否像标题。"""
    if not text:
        return False
    stripped = text.strip()
    if len(stripped) > 80:
        return False
    if stripped.endswith(_SENTENCE_ENDS):
        return False
    for pat in patterns:
        if pat.match(stripped):
            return True
    return False


def mark_headings(elements: list[MDElement], cfg: dict) -> list[MDElement]:
    """增强标题检测：Markdown # 语法 + 正则模式匹配。

    修改 elements 的 is_heading 和 level 字段。
    """
    smart_cfg = cfg.get("smart_split", {})
    custom_regex = smart_cfg.get("custom_heading_regex", "")
    patterns = _compile_patterns(custom_regex)

    for elem in elements:
        if elem["is_heading"]:
            continue
        if elem["type"] in ("blank", "code", "table"):
            continue
        plain = elem["text"].lstrip("#").strip()
        if _content_looks_like_heading(plain, patterns):
            elem["is_heading"] = True
            if elem["level"] is None:
                elem["level"] = 0

    return elements
