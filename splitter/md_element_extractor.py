"""Markdown 元素提取器 — 将 Markdown 文本解析为结构化元素流。"""

import re
from typing import Literal, TypedDict


class MDElement(TypedDict):
    idx: int
    type: Literal["heading", "paragraph", "list", "table", "code", "blockquote", "blank"]
    text: str
    length: int
    level: int | None
    is_heading: bool
    ends_with_period: bool


_RE_HEADING = re.compile(r"^(#{1,6})\s+(.*)$")
_RE_LIST_ITEM = re.compile(r"^(\s*)([-*+]|\d+[.\)])\s+")
_RE_CODE_FENCE = re.compile(r"^```")
_RE_BLOCKQUOTE = re.compile(r"^>\s?")
_RE_TABLE_ROW = re.compile(r"^\|.*\|$")
_RE_TABLE_SEP = re.compile(r"^\|[\s\-:]+\|$")

_SENTENCE_ENDS = (".", "!", "?", "。", "！", "？", "；", ";")


def extract_elements(md_text: str) -> list[MDElement]:
    """将 Markdown 文本拆分为元素列表。

    每个"元素"对应一个语义块（标题/段落/列表项/表格/代码块/引用/空行）。
    """
    lines = md_text.split("\n")
    elements: list[MDElement] = []
    idx = 0
    i = 0

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        # 空行
        if not stripped:
            elements.append(_make_element(idx, "blank", "", 0))
            idx += 1
            i += 1
            continue

        # 代码块
        if _RE_CODE_FENCE.match(stripped):
            code_lines = [line]
            i += 1
            while i < len(lines):
                code_lines.append(lines[i])
                if _RE_CODE_FENCE.match(lines[i].strip()) and len(code_lines) > 1:
                    i += 1
                    break
                i += 1
            text = "\n".join(code_lines)
            elements.append(_make_element(idx, "code", text, len(text)))
            idx += 1
            continue

        # 标题
        m = _RE_HEADING.match(stripped)
        if m:
            level = len(m.group(1))
            text = m.group(2).strip()
            el = _make_element(idx, "heading", stripped, len(stripped))
            el["level"] = level
            el["is_heading"] = True
            elements.append(el)
            idx += 1
            i += 1
            continue

        # 表格
        if _RE_TABLE_ROW.match(stripped):
            table_lines = []
            while i < len(lines) and (_RE_TABLE_ROW.match(lines[i].strip()) or _RE_TABLE_SEP.match(lines[i].strip())):
                table_lines.append(lines[i])
                i += 1
            text = "\n".join(table_lines)
            elements.append(_make_element(idx, "table", text, len(text)))
            idx += 1
            continue

        # 引用块
        if _RE_BLOCKQUOTE.match(stripped):
            bq_lines = []
            while i < len(lines) and _RE_BLOCKQUOTE.match(lines[i].strip()):
                bq_lines.append(lines[i])
                i += 1
            text = "\n".join(bq_lines)
            elements.append(_make_element(idx, "blockquote", text, len(text)))
            idx += 1
            continue

        # 列表项
        if _RE_LIST_ITEM.match(stripped):
            list_lines = [line]
            i += 1
            while i < len(lines):
                next_stripped = lines[i].strip()
                if not next_stripped:
                    break
                if _RE_LIST_ITEM.match(next_stripped) or lines[i].startswith("  "):
                    list_lines.append(lines[i])
                    i += 1
                else:
                    break
            text = "\n".join(list_lines)
            elements.append(_make_element(idx, "list", text, len(text)))
            idx += 1
            continue

        # 普通段落（合并连续非空行）
        para_lines = [line]
        i += 1
        while i < len(lines):
            next_line = lines[i]
            next_stripped = next_line.strip()
            if not next_stripped:
                break
            if _RE_HEADING.match(next_stripped):
                break
            if _RE_CODE_FENCE.match(next_stripped):
                break
            if _RE_TABLE_ROW.match(next_stripped):
                break
            if _RE_BLOCKQUOTE.match(next_stripped):
                break
            if _RE_LIST_ITEM.match(next_stripped):
                break
            para_lines.append(next_line)
            i += 1
        text = "\n".join(para_lines)
        elements.append(_make_element(idx, "paragraph", text, len(text)))
        idx += 1

    return elements


def _make_element(
    idx: int,
    elem_type: str,
    text: str,
    length: int,
) -> MDElement:
    return MDElement(
        idx=idx,
        type=elem_type,
        text=text,
        length=length,
        level=None,
        is_heading=elem_type == "heading",
        ends_with_period=text.rstrip().endswith(_SENTENCE_ENDS) if text else False,
    )
