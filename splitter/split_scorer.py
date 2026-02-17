"""分割评分器 — 多维评分 + 阈值切分 + 后处理。

借鉴 VerbaAurea 的 find_split_points / calculate_split_score / refine_split_points /
merge_heading_with_body 四大函数。
"""

from splitter.md_element_extractor import MDElement
from splitter.sentence_boundary import (
    find_nearest_sentence_boundary,
    is_sentence_boundary,
)


def find_split_points(elements: list[MDElement], cfg: dict) -> list[int]:
    """寻找分割点，返回元素索引列表。"""
    sc = cfg.get("smart_split", {})
    max_length = sc.get("max_length", 1200)
    min_length = sc.get("min_length", 300)
    min_split_score = sc.get("min_split_score", 7.0)
    heading_score_bonus = sc.get("heading_score_bonus", 10.0)
    sentence_end_score_bonus = sc.get("sentence_end_score_bonus", 6.0)
    sentence_integrity_weight = sc.get("sentence_integrity_weight", 8.0)
    length_score_factor = sc.get("length_score_factor", 100)
    search_window = sc.get("search_window", 5)
    heading_after_penalty = sc.get("heading_after_penalty", 12.0)
    force_heading = sc.get("force_split_before_heading", True)
    cooldown_len = sc.get("heading_cooldown_elements", 2)

    split_points: list[int] = []
    current_length = 0
    last_potential = -1
    cooldown = 0

    for idx, elem in enumerate(elements):
        # 标题强制分段
        if elem["is_heading"] and idx > 0 and force_heading:
            if not split_points or idx != split_points[-1]:
                split_points.append(idx)
            current_length = 0
            last_potential = idx
            cooldown = cooldown_len
            continue

        # 空行：仅累长
        if elem["length"] == 0:
            current_length += elem["length"]
            continue

        # 冷却阶段：仅累长，不打分
        if cooldown > 0:
            current_length += elem["length"]
            cooldown -= 1
            continue

        current_length += elem["length"]

        # 计算得分
        score = _calculate_score(
            idx,
            elem,
            elements,
            current_length,
            min_length,
            max_length,
            sentence_integrity_weight,
            heading_score_bonus,
            sentence_end_score_bonus,
            length_score_factor,
            heading_after_penalty,
            split_points,
        )

        if score >= min_split_score and idx > 0:
            split_points.append(idx)
            current_length = 0
            last_potential = idx
        elif current_length > max_length * 1.5:
            best = find_nearest_sentence_boundary(elements, idx, search_window)
            if best >= 0 and (not split_points or best > split_points[-1]):
                split_points.append(best)
                current_length = 0
                last_potential = best
            elif idx - last_potential > 3:
                split_points.append(idx)
                current_length = 0
                last_potential = idx

    return split_points


def _calculate_score(
    idx: int,
    elem: MDElement,
    elements: list[MDElement],
    current_length: int,
    min_length: int,
    max_length: int,
    sentence_integrity_weight: float,
    heading_score_bonus: float,
    sentence_end_score_bonus: float,
    length_score_factor: int,
    heading_after_penalty: float,
    split_points: list[int],
) -> float:
    score = 0.0

    if elem["type"] in ("paragraph", "list", "blockquote"):
        if elem["is_heading"]:
            score += heading_score_bonus
        if elem["ends_with_period"]:
            score += sentence_end_score_bonus

        if idx > 0 and elements[idx - 1]["type"] in ("paragraph", "list", "blockquote"):
            if is_sentence_boundary(elements[idx - 1]["text"], elem["text"]):
                score += sentence_integrity_weight
            else:
                score -= 10
    else:
        score += 6  # 表格/代码块基分

    # 紧跟标题扣分
    prev = idx - 1
    while prev >= 0 and elements[prev]["length"] == 0:
        prev -= 1
    if prev >= 0 and elements[prev]["is_heading"]:
        score -= heading_after_penalty

    # 长度因子
    if current_length >= min_length:
        score += min(4, (current_length - min_length) // length_score_factor)
    elif current_length < min_length * 0.7:
        score -= 5

    # 距上个分割点太近
    if split_points and idx - split_points[-1] < 3:
        score -= 8

    # 超长补分
    if current_length > max_length:
        score += 4

    return score


def refine_split_points(
    elements: list[MDElement],
    split_points: list[int],
    cfg: dict,
) -> list[int]:
    """后处理：确保分割点不会打断句子。"""
    search_window = cfg.get("smart_split", {}).get("search_window", 5)
    refined = []

    for sp in split_points:
        if elements[sp]["is_heading"]:
            refined.append(sp)
            continue
        if sp > 0 and elements[sp - 1]["is_heading"]:
            refined.append(sp)
            continue

        need_adjust = False
        if (
            sp > 0
            and elements[sp - 1]["type"] in ("paragraph", "list")
            and elements[sp]["type"] in ("paragraph", "list")
        ):
            need_adjust = not is_sentence_boundary(
                elements[sp - 1]["text"], elements[sp]["text"]
            )

        if need_adjust:
            best = find_nearest_sentence_boundary(elements, sp, search_window)
            refined.append(best if best >= 0 else sp)
        else:
            refined.append(sp)

    return sorted(set(refined))


def merge_heading_with_body(
    elements: list[MDElement],
    split_points: list[int],
) -> list[int]:
    """保证"标题 + 首块内容"不被拆开。"""
    if not split_points:
        return []

    keep = set(split_points)

    for sp in split_points:
        i = sp - 1
        while i >= 0 and elements[i]["length"] == 0:
            i -= 1

        if i >= 0 and elements[i]["is_heading"]:
            heading_idx = i
            j = heading_idx + 1
            while j < len(elements) and elements[j]["length"] == 0:
                j += 1
            first_content_idx = j
            if heading_idx < sp <= first_content_idx:
                keep.discard(sp)

    return sorted(keep)
