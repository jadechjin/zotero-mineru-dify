"""智能分割 pipeline — 串联 5 个子模块完成 Markdown 智能分割。"""

import logging

from splitter.md_element_extractor import extract_elements
from splitter.heading_detector import mark_headings
from splitter.split_scorer import (
    find_split_points,
    merge_heading_with_body,
    refine_split_points,
)
from splitter.split_renderer import render_with_markers

logger = logging.getLogger(__name__)


def smart_split(md_text: str, cfg: dict) -> tuple[str, dict]:
    """对单篇 Markdown 执行智能分割。

    Args:
        md_text: 清洗后的 Markdown 文本。
        cfg: 完整配置快照。

    Returns:
        (marked_md, stats)
    """
    smart_cfg = cfg.get("smart_split", {})
    if not smart_cfg.get("enabled", True):
        return md_text, {"split_count": 0, "skipped": True}

    marker = smart_cfg.get("split_marker", "<!--split-->")

    elements = extract_elements(md_text)
    elements = mark_headings(elements, cfg)
    points = find_split_points(elements, cfg)
    points = refine_split_points(elements, points, cfg)
    points = merge_heading_with_body(elements, points)
    marked_md, stats = render_with_markers(md_text, elements, points, marker)

    logger.debug(
        "智能分割完成：%d 个元素，%d 个分割点，平均段长 %.0f",
        stats["total_elements"],
        stats["split_count"],
        stats["avg_segment_length"],
    )
    return marked_md, stats


def smart_split_all(
    md_results: dict, cfg: dict
) -> tuple[dict, dict]:
    """批量智能分割。

    Args:
        md_results: {key: {"text": str, "file_name": str, ...}}
        cfg: 完整配置快照。

    Returns:
        (split_results, aggregate_stats)
    """
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
            logger.warning("智能分割失败 '%s'，保留原文: %s", data.get("file_name", key), exc)
            marked_text = original_text

        split_results[key] = {**data, "text": marked_text}

    agg = {
        "total_splits": total_splits,
        "file_count": len(md_results),
    }
    return split_results, agg
