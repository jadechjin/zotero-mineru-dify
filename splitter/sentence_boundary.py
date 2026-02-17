"""句边界检测 — 中文 jieba + 英文标点启发式。"""

import functools
import logging

logger = logging.getLogger(__name__)

_SENTENCE_ENDS = frozenset("。！？.!?；;")

# 延迟加载 jieba / nltk，避免未安装时启动报错
_jieba = None
_nltk_sent_tokenize = None


def _lazy_jieba():
    global _jieba
    if _jieba is None:
        try:
            import jieba as _j
            _j.setLogLevel(logging.WARNING)
            _jieba = _j
        except ImportError:
            _jieba = False
    return _jieba if _jieba is not False else None


def _lazy_nltk():
    global _nltk_sent_tokenize
    if _nltk_sent_tokenize is None:
        try:
            import nltk
            try:
                nltk.data.find("tokenizers/punkt_tab")
            except LookupError:
                nltk.download("punkt_tab", quiet=True)
            from nltk.tokenize import sent_tokenize
            _nltk_sent_tokenize = sent_tokenize
        except ImportError:
            _nltk_sent_tokenize = False
    return _nltk_sent_tokenize if _nltk_sent_tokenize is not False else None


@functools.lru_cache(maxsize=2048)
def is_sentence_boundary(text_before: str, text_after: str) -> bool:
    """判断两段文本之间是否为句子边界。

    借鉴 VerbaAurea 的 jieba/nltk 双重检测策略。
    """
    if not text_before:
        return True

    last_char = text_before.rstrip()[-1] if text_before.rstrip() else ""
    if last_char in _SENTENCE_ENDS:
        return True

    combined = text_before + " " + text_after
    has_cjk = any("\u4e00" <= c <= "\u9fff" for c in combined)

    if has_cjk:
        jb = _lazy_jieba()
        if jb:
            try:
                words = list(jb.cut(combined))
                for i, w in enumerate(words[:-1]):
                    if w in _SENTENCE_ENDS:
                        before_seg = "".join(words[: i + 1])
                        if abs(len(before_seg) - len(text_before)) < 5:
                            return True
            except Exception:
                pass
    else:
        sent_tok = _lazy_nltk()
        if sent_tok:
            try:
                sents = sent_tok(combined)
                for s in sents:
                    if text_before.endswith(s) or text_after.startswith(s):
                        return True
            except Exception:
                pass

    return False


def find_nearest_sentence_boundary(
    elements: list, current_index: int, search_window: int = 5
) -> int:
    """在 elements 中寻找距 current_index 最近的句边界。"""
    best = -1
    best_dist = float("inf")

    start = max(0, current_index - search_window)
    end = min(len(elements), current_index + search_window + 1)

    for i in range(start, end):
        if i <= 0:
            continue
        prev_text = elements[i - 1]["text"]
        cur_text = elements[i]["text"]
        if not prev_text or not cur_text:
            continue
        if is_sentence_boundary(prev_text, cur_text):
            d = abs(i - current_index)
            if d < best_dist:
                best_dist = d
                best = i

    return best
