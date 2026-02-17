"""分割渲染器 — 在 Markdown 文本中插入 <!--split--> 标记。"""

from splitter.md_element_extractor import MDElement


def render_with_markers(
    md_text: str,
    elements: list[MDElement],
    split_points: list[int],
    marker: str = "<!--split-->",
) -> tuple[str, dict]:
    """在原始 Markdown 中按分割点插入标记。

    Returns:
        (marked_md, stats) 其中 stats 含 total_elements、split_count、
        avg_segment_length。
    """
    if not split_points or not elements:
        return md_text, {
            "total_elements": len(elements),
            "split_count": 0,
            "avg_segment_length": len(md_text),
        }

    split_set = set(split_points)
    lines = md_text.split("\n")
    result_parts: list[str] = []
    line_cursor = 0

    for elem in elements:
        if elem["idx"] in split_set and result_parts:
            result_parts.append(marker)

        elem_text = elem["text"]
        elem_lines = elem_text.split("\n") if elem_text else [""]
        num_lines = len(elem_lines)

        chunk = "\n".join(lines[line_cursor: line_cursor + num_lines])
        result_parts.append(chunk)
        line_cursor += num_lines

    # 残余行
    if line_cursor < len(lines):
        remainder = "\n".join(lines[line_cursor:])
        if remainder.strip():
            result_parts.append(remainder)

    marked = "\n".join(result_parts)
    split_count = len(split_points)
    avg_len = len(marked) / (split_count + 1) if split_count > 0 else len(marked)

    stats = {
        "total_elements": len(elements),
        "split_count": split_count,
        "avg_segment_length": round(avg_len, 1),
    }
    return marked, stats
