"""Smart split pipeline for Markdown segmentation."""

import bisect
import logging
import re

from splitter.heading_detector import mark_headings
from splitter.md_element_extractor import extract_elements
from splitter.split_renderer import render_with_markers
from splitter.split_scorer import (
    find_split_points,
    merge_heading_with_body,
    refine_split_points,
)

logger = logging.getLogger(__name__)

_RE_MD_HEADING = re.compile(r"^(#{1,6})\s*(.+?)\s*$")
_RE_NUMBER_HEADING = re.compile(r"^\s*(?:\d+(?:\.\d+)*)[\s\-_.:：)]*\s*(.+)$")
_RE_PAGE_NUMBER = re.compile(r"^\s*\d{1,4}\s*$")
_SENTENCE_END = (".", "!", "?", "\u3002", "\uff01", "\uff1f", ":", "\uff1a", ";", "\uff1b")
_HARD_SPLIT_STEP_CHARS = 300_000
_DOC_SPLIT_MAX_CHARS = 300_000


def smart_split(md_text: str, cfg: dict) -> tuple[str, dict]:
    """Split one markdown document according to configured strategy."""
    smart_cfg = cfg.get("smart_split", {})
    if not smart_cfg.get("enabled", True):
        return md_text, {"split_count": 0, "skipped": True}

    marker = smart_cfg.get("split_marker", "<!--split-->")
    strategy = str(smart_cfg.get("strategy", "paragraph_wrap") or "paragraph_wrap").strip().lower()

    # Keep this order: normalize headings first, then apply 300k-based heading split.
    normalized_text = _normalize_heading_levels(_strip_existing_markers(md_text, marker))
    sections, hard_split_count = _split_text_by_heading_size(normalized_text, _HARD_SPLIT_STEP_CHARS)

    if strategy == "paragraph_wrap":
        marked_md, stats = _paragraph_wrap_split(
            normalized_text,
            marker,
            pre_normalized=True,
            sections=sections,
        )
        stats["hard_split_count"] = hard_split_count
        logger.debug(
            "paragraph_wrap complete: segments=%d, split_markers=%d, hard_splits=%d",
            stats["segment_count"],
            stats["split_count"],
            hard_split_count,
        )
        return marked_md, stats

    marked_parts = []
    total_elements = 0
    total_splits = 0

    for section in sections:
        if not section.strip():
            continue

        elements = extract_elements(section)
        elements = mark_headings(elements, cfg)
        points = find_split_points(elements, cfg)
        points = refine_split_points(elements, points, cfg)
        points = merge_heading_with_body(elements, points)
        marked_part, part_stats = render_with_markers(section, elements, points, marker)

        marked_parts.append(marked_part.strip())
        total_elements += part_stats.get("total_elements", len(elements))
        total_splits += part_stats.get("split_count", 0)

    if not marked_parts:
        return normalized_text.strip(), {
            "total_elements": 0,
            "split_count": 0,
            "avg_segment_length": len(normalized_text),
            "hard_split_count": hard_split_count,
            "strategy": "semantic",
        }

    boundary_splits = max(0, len(marked_parts) - 1)
    marked_md = _join_sections_with_marker(marked_parts, marker)
    total_split_count = total_splits + boundary_splits
    stats = {
        "total_elements": total_elements,
        "split_count": total_split_count,
        "avg_segment_length": round(len(marked_md) / max(1, total_split_count + 1), 1),
        "hard_split_count": hard_split_count,
        "strategy": "semantic",
    }

    logger.debug(
        "semantic split complete: total_elements=%d, split_count=%d, avg_segment_length=%.0f, hard_splits=%d",
        stats["total_elements"],
        stats["split_count"],
        stats["avg_segment_length"],
        hard_split_count,
    )
    return marked_md, stats


def _paragraph_wrap_split(
    md_text: str,
    marker: str,
    pre_normalized: bool = False,
    sections: list[str] | None = None,
) -> tuple[str, dict]:
    if pre_normalized:
        text = md_text
    else:
        text = _normalize_heading_levels(_strip_existing_markers(md_text, marker))

    split_sections = sections if sections is not None else _split_text_by_heading_size(text, _HARD_SPLIT_STEP_CHARS)[0]

    blocks = []
    for section in split_sections:
        section_blocks = _collect_blocks(section)
        section_blocks = _merge_cross_page_paragraphs(section_blocks)
        blocks.extend(section_blocks)

    if not blocks:
        return text.strip(), {
            "total_elements": 0,
            "split_count": 0,
            "avg_segment_length": len(text),
            "segment_count": 0,
            "strategy": "paragraph_wrap",
        }

    wrapped_blocks = [f"{marker}\n{block.strip()}\n{marker}" for block in blocks if block.strip()]
    marked = "\n\n".join(wrapped_blocks).strip()

    segment_count = len(wrapped_blocks)
    split_count = segment_count * 2
    avg_len = len(marked) / max(1, segment_count)

    return marked, {
        "total_elements": segment_count,
        "split_count": split_count,
        "avg_segment_length": round(avg_len, 1),
        "segment_count": segment_count,
        "strategy": "paragraph_wrap",
    }


def _strip_existing_markers(text: str, marker: str) -> str:
    lines = []
    marker_plain = marker.strip()
    for line in text.split("\n"):
        if line.strip() == marker_plain:
            continue
        lines.append(line)
    return "\n".join(lines)


def _normalize_heading_levels(text: str) -> str:
    lines = text.split("\n")
    out = []
    i = 0

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        match = _RE_MD_HEADING.match(stripped)
        if not match:
            out.append(line)
            i += 1
            continue

        run = [match]
        j = i + 1
        while j < len(lines):
            probe = lines[j].strip()
            if not probe:
                k = j + 1
                while k < len(lines) and not lines[k].strip():
                    k += 1
                if k < len(lines) and _RE_MD_HEADING.match(lines[k].strip()):
                    j = k
                    continue
                break

            probe_match = _RE_MD_HEADING.match(probe)
            if not probe_match:
                break
            run.append(probe_match)
            j += 1

        min_level = min(len(m.group(1)) for m in run)
        kept_top = False

        for m in run:
            title = (m.group(2) or "").strip()
            level = len(m.group(1))

            if not kept_top and level == min_level:
                out.append(f"# {title}")
                kept_top = True
            else:
                out.append(_strip_heading_numbering(title))

        i = j

    return "\n".join(out)


def _strip_heading_numbering(title: str) -> str:
    probe = (title or "").strip()
    if not probe:
        return ""

    matched = _RE_NUMBER_HEADING.match(probe)
    if matched:
        cleaned = matched.group(1).strip()
        if cleaned:
            return cleaned
    return probe


def _split_text_by_heading_size(text: str, step_chars: int) -> tuple[list[str], int]:
    """Split long text near heading lines around each step_chars multiple."""
    if not text:
        return [""], 0
    if step_chars <= 0 or len(text) <= step_chars:
        return [text], 0

    lines = text.split("\n")
    heading_positions = []

    char_offset = 0
    for idx, line in enumerate(lines):
        if line.strip().startswith("# "):
            heading_positions.append((idx, char_offset))
        char_offset += len(line)
        if idx < len(lines) - 1:
            char_offset += 1

    if not heading_positions:
        return [text], 0

    cut_lines = []
    min_line_idx = 1
    for target in range(step_chars, len(text), step_chars):
        cut_line = _pick_nearest_heading_line(heading_positions, target, min_line_idx)
        if cut_line is None:
            break
        if cut_lines and cut_line == cut_lines[-1]:
            continue
        cut_lines.append(cut_line)
        min_line_idx = cut_line + 1

    if not cut_lines:
        return [text], 0

    sections = []
    start = 0
    for line_idx in cut_lines:
        chunk = "\n".join(lines[start:line_idx]).strip()
        if chunk:
            sections.append(chunk)
        start = line_idx

    tail = "\n".join(lines[start:]).strip()
    if tail:
        sections.append(tail)

    if not sections:
        return [text], 0
    return sections, len(cut_lines)


def _pick_nearest_heading_line(
    heading_positions: list[tuple[int, int]],
    target_offset: int,
    min_line_idx: int,
) -> int | None:
    best = None
    for line_idx, char_offset in heading_positions:
        if line_idx < min_line_idx or char_offset <= 0:
            continue
        candidate = (abs(char_offset - target_offset), char_offset, line_idx)
        if best is None or candidate < best:
            best = candidate
    if best is None:
        return None
    return best[2]


def _join_sections_with_marker(parts: list[str], marker: str) -> str:
    cleaned = [p.strip() for p in parts if p and p.strip()]
    if not cleaned:
        return ""

    output = cleaned[0]
    for part in cleaned[1:]:
        if output.rstrip().endswith(marker):
            output = output.rstrip() + "\n" + part
        elif part.lstrip().startswith(marker):
            output = output.rstrip() + "\n" + part.lstrip()
        else:
            output = output.rstrip() + f"\n{marker}\n" + part.lstrip()
    return output


def _collect_blocks(text: str) -> list[str]:
    lines = text.split("\n")
    blocks = []
    current = []
    in_code = False

    def flush_current():
        if not current:
            return
        block = "\n".join(current).strip()
        if block:
            blocks.append(block)
        current.clear()

    for raw_line in lines:
        line = raw_line.rstrip()
        stripped = line.strip()

        if stripped == "\f":
            continue
        if _RE_PAGE_NUMBER.match(stripped):
            continue

        if stripped.startswith("```"):
            if not in_code:
                flush_current()
                in_code = True
                current.append(line)
            else:
                current.append(line)
                flush_current()
                in_code = False
            continue

        if in_code:
            current.append(line)
            continue

        if not stripped:
            flush_current()
            continue

        if stripped.startswith("# "):
            flush_current()
            blocks.append(stripped)
            continue

        if _is_block_starter(stripped) and current and not _is_same_block_type(current[-1], stripped):
            flush_current()

        current.append(line)

    flush_current()
    return blocks


def _is_block_starter(line: str) -> bool:
    return (
        line.startswith("- ")
        or line.startswith("* ")
        or line.startswith(">")
        or line.startswith("|")
        or bool(re.match(r"^\d+[.)]\s+", line))
    )


def _is_same_block_type(prev_line: str, new_line: str) -> bool:
    prev = prev_line.strip()
    new = new_line.strip()

    if prev.startswith(("- ", "* ")) and new.startswith(("- ", "* ")):
        return True
    if bool(re.match(r"^\d+[.)]\s+", prev)) and bool(re.match(r"^\d+[.)]\s+", new)):
        return True
    if prev.startswith(">") and new.startswith(">"):
        return True
    if prev.startswith("|") and new.startswith("|"):
        return True

    return False


def _merge_cross_page_paragraphs(blocks: list[str]) -> list[str]:
    if not blocks:
        return []

    merged = [blocks[0]]
    for block in blocks[1:]:
        prev = merged[-1]
        if _should_merge_paragraph(prev, block):
            merged[-1] = _join_paragraphs(prev, block)
        else:
            merged.append(block)
    return merged


def _should_merge_paragraph(prev: str, curr: str) -> bool:
    if not prev or not curr:
        return False
    if prev.lstrip().startswith("# ") or curr.lstrip().startswith("# "):
        return False
    if prev.lstrip().startswith(("- ", "* ", ">", "|")):
        return False
    if curr.lstrip().startswith(("- ", "* ", ">", "|")):
        return False
    if prev.rstrip().endswith(_SENTENCE_END):
        return False

    curr_head = curr.strip()[:24].lower()
    merge_starters = (
        "and ",
        "or ",
        "with ",
        "where ",
        "which ",
        "that ",
        "while ",
        "because ",
        "\u5e76",
        "\u6216",
        "\u4ee5\u53ca",
        "\u5176\u4e2d",
        "\u5e76\u4e14",
        "\u800c\u4e14",
    )

    if curr and curr[0].islower():
        return True
    if curr_head.startswith(merge_starters):
        return True

    return False


def _join_paragraphs(prev: str, curr: str) -> str:
    prev_text = prev.rstrip()
    curr_text = curr.lstrip()

    if not prev_text:
        return curr_text
    if not curr_text:
        return prev_text

    if _is_cjk_char(prev_text[-1]) and _is_cjk_char(curr_text[0]):
        return prev_text + curr_text
    return prev_text + " " + curr_text


def _is_cjk_char(ch: str) -> bool:
    if not ch:
        return False
    code = ord(ch)
    return 0x4E00 <= code <= 0x9FFF


def smart_split_all(md_results: dict, cfg: dict) -> tuple[dict, dict]:
    """Batch smart split."""
    smart_cfg = cfg.get("smart_split", {})
    if not smart_cfg.get("enabled", True):
        return md_results, {"total_splits": 0, "file_count": len(md_results), "skipped": True}

    split_results = {}
    total_splits = 0

    for key, data in md_results.items():
        original_text = data.get("text", "")
        try:
            marked_text, stats = smart_split(original_text, cfg)
            total_splits += stats.get("split_count", 0)
        except Exception as exc:
            logger.warning("smart split failed for '%s', keep original: %s", data.get("file_name", key), exc)
            marked_text = original_text

        split_results[key] = {**data, "text": marked_text}

    agg = {
        "total_splits": total_splits,
        "file_count": len(md_results),
    }
    return split_results, agg


def split_documents_for_upload(
    md_results: dict,
    cfg: dict,
    max_chars: int = _DOC_SPLIT_MAX_CHARS,
) -> tuple[dict, dict]:
    """Split large markdown documents into multiple upload documents."""
    marker = cfg.get("smart_split", {}).get("split_marker", "<!--split-->")
    max_chars = max(10_000, int(max_chars or _DOC_SPLIT_MAX_CHARS))

    output = {}
    split_source_files = 0
    total_parts = 0
    heading_cuts = 0
    hard_cuts = 0

    for key, data in md_results.items():
        original_text = data.get("text", "") or ""
        normalized = _normalize_heading_levels(original_text)
        parts, part_stats = _split_text_into_upload_docs(
            normalized,
            marker=marker,
            max_chars=max_chars,
        )

        total_parts += len(parts)
        heading_cuts += part_stats.get("heading_cuts", 0)
        hard_cuts += part_stats.get("hard_cuts", 0)

        if len(parts) <= 1:
            output[key] = {**data, "text": parts[0] if parts else normalized}
            continue

        split_source_files += 1
        source_name = data.get("file_name", key)
        for idx, part_text in enumerate(parts, start=1):
            part_key = f"{key}#part{idx}"
            output[part_key] = {
                **data,
                "text": part_text,
                "file_name": _build_part_file_name(source_name, idx, len(parts)),
                "source_file_name": source_name,
                "parent_task_key": key,
                "part_index": idx,
                "part_total": len(parts),
            }

    stats = {
        "max_chars": max_chars,
        "source_files": len(md_results),
        "output_docs": len(output),
        "split_source_files": split_source_files,
        "total_parts": total_parts,
        "heading_cuts": heading_cuts,
        "hard_cuts": hard_cuts,
    }
    return output, stats


def _split_text_into_upload_docs(text: str, marker: str, max_chars: int) -> tuple[list[str], dict]:
    normalized = _strip_existing_markers(text or "", marker)
    if len(normalized) <= max_chars:
        return [normalized], {"heading_cuts": 0, "hard_cuts": 0}

    lines = normalized.split("\n")
    if not lines:
        return [normalized], {"heading_cuts": 0, "hard_cuts": 0}

    line_offsets = _line_start_offsets(lines)
    headings = [(idx, line_offsets[idx]) for idx, line in enumerate(lines) if line.strip().startswith("# ")]

    parts = []
    heading_cuts = 0
    hard_cuts = 0
    start_line = 0
    total_len = len(normalized)

    while start_line < len(lines):
        start_offset = line_offsets[start_line]
        remaining = total_len - start_offset
        if remaining <= max_chars:
            tail = "\n".join(lines[start_line:]).strip()
            if tail:
                parts.append(tail)
            break

        target = start_offset + max_chars
        cut_line = _pick_doc_cut_line(headings, line_offsets, start_line, target)
        if cut_line is not None and line_offsets[cut_line] - start_offset <= max_chars:
            heading_cuts += 1
        else:
            cut_line = _line_at_or_before_offset(line_offsets, target, min_line=start_line + 1)
            hard_cuts += 1

        if cut_line <= start_line:
            cut_line = min(len(lines), start_line + 1)

        chunk = "\n".join(lines[start_line:cut_line]).strip()
        if chunk:
            parts.append(chunk)
        start_line = cut_line

    if not parts:
        return [normalized], {"heading_cuts": 0, "hard_cuts": 0}

    safe_parts = []
    for part in parts:
        if len(part) <= max_chars:
            safe_parts.append(part)
            continue
        start = 0
        while start < len(part):
            safe_parts.append(part[start:start + max_chars])
            start += max_chars
            hard_cuts += 1

    return safe_parts, {"heading_cuts": heading_cuts, "hard_cuts": hard_cuts}


def _line_start_offsets(lines: list[str]) -> list[int]:
    offsets = []
    cursor = 0
    for idx, line in enumerate(lines):
        offsets.append(cursor)
        cursor += len(line)
        if idx < len(lines) - 1:
            cursor += 1
    return offsets


def _pick_doc_cut_line(
    headings: list[tuple[int, int]],
    line_offsets: list[int],
    start_line: int,
    target_offset: int,
) -> int | None:
    prev_heading = None
    next_heading = None
    for line_idx, offset in headings:
        if line_idx <= start_line:
            continue
        if offset <= target_offset:
            prev_heading = (line_idx, offset)
            continue
        next_heading = (line_idx, offset)
        break

    if prev_heading is None and next_heading is None:
        return None
    if prev_heading is None:
        return next_heading[0]
    if next_heading is None:
        return prev_heading[0]

    prev_dist = target_offset - prev_heading[1]
    next_dist = next_heading[1] - target_offset
    if prev_dist <= next_dist:
        return prev_heading[0]
    return next_heading[0]


def _line_at_or_before_offset(line_offsets: list[int], target_offset: int, min_line: int) -> int:
    idx = bisect.bisect_right(line_offsets, target_offset) - 1
    if idx < min_line:
        idx = min_line
    if idx >= len(line_offsets):
        idx = len(line_offsets) - 1
    return idx


def _build_part_file_name(file_name: str, part_index: int, total_parts: int) -> str:
    base = file_name or "document.md"
    stem, ext = re.match(r"^(.*?)(\.[^.]+)?$", base).groups()
    ext = ext or ".md"
    return f"{stem}.part{part_index}of{total_parts}{ext}"
