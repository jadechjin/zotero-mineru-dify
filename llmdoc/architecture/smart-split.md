# Smart Split Pipeline Architecture

## Overview

The smart split module (`splitter/`) provides semantic-aware Markdown text splitting, inspired by [VerbaAurea](https://github.com/VerbaAurea/VerbaAurea). It replaces simple separator-based chunking with structure-aware splitting that respects heading boundaries and sentence integrity.

## Pipeline Flow

```
Markdown text
    │
    ▼
md_element_extractor.extract_elements()
    │  Parses into MDElement[] (heading, paragraph, list, table, code, blockquote, blank)
    ▼
heading_detector.mark_headings()
    │  Enriches is_heading flags using Markdown # syntax + configurable regex
    ▼
split_scorer.find_split_points()
    │  Scores every element boundary with multi-dimensional formula
    │  Uses sentence_boundary.is_sentence_boundary() for integrity checks
    ▼
split_scorer.refine_split_points()
    │  Applies merge_heading_with_body() and cooldown filtering
    ▼
split_renderer.render_with_markers()
    │  Inserts <!--split--> markers at chosen split points
    ▼
Split Markdown text (with markers)
```

## Sub-modules

### md_element_extractor.py

- Input: Raw Markdown string
- Output: `list[MDElement]` where MDElement is a TypedDict:
  ```python
  class MDElement(TypedDict):
      idx: int
      type: Literal["heading", "paragraph", "list", "table", "code", "blockquote", "blank"]
      text: str
      length: int
      level: int | None      # Heading level (1-6) or None
      is_heading: bool
      ends_with_period: bool
  ```
- Handles: `#` headings, paragraphs, `- / * / 1.` lists, `|` tables, ` ``` ` code blocks, `>` blockquotes, blank lines

### heading_detector.py

- Enriches `is_heading` flags beyond Markdown `#` syntax
- Default regex patterns (Chinese): `^第[一二三四五六七八九十百千万\d]+[章节篇部分]`, `^[一二三四五六七八九十]+[、.]`
- Configurable via `cfg["smart_split"]["custom_heading_regex"]`

### sentence_boundary.py

- `is_sentence_boundary(text_before, text_after) -> bool`
- Uses jieba (Chinese) and NLTK punkt (English) for sentence tokenization
- Lazy loading: jieba/NLTK imported on first use to avoid startup errors
- LRU cached (2048 entries)
- `find_nearest_sentence_boundary(elements, idx, window) -> int`

### split_scorer.py

- `find_split_points(elements, cfg) -> list[int]`
- Scoring formula per boundary:
  ```
  score = heading_bonus (if next is heading)
        + sentence_end_bonus (if current ends with period)
        + sentence_integrity_weight * is_sentence_boundary()
        + accumulated_length / length_score_factor
        - heading_after_penalty (if splitting right after a heading)
        - cooldown penalty (if too close to last split)
  ```
- Split when `score >= min_split_score` AND `accumulated_length >= min_length`
- Force split when `accumulated_length >= max_length`
- `refine_split_points()`: Post-processing to merge lone headings with following body

### split_renderer.py

- `render_with_markers(md_text, elements, split_points, marker) -> (str, stats)`
- Maps element indices back to original text line positions
- Inserts marker string between elements at split points
- Returns modified text + statistics dict

## Dify Coordination

When `smart_split.enabled = true`, `pipeline_runner.py`:
1. Runs smart_split_all() on Markdown results
2. Deep-copies cfg, overrides `cfg["dify"]["segment_separator"]` to the split marker
3. Passes modified cfg to `upload_all()` — Dify chunks on `<!--split-->` boundaries

## Configuration

All smart split params live under `cfg["smart_split"]`:

| Key | Default | Description |
|-----|---------|-------------|
| enabled | true | Enable/disable smart splitting |
| split_marker | `<!--split-->` | Marker inserted at split points |
| max_length | 1200 | Force split above this length |
| min_length | 300 | Don't split below this length |
| min_split_score | 7.0 | Minimum score to trigger split |
| heading_score_bonus | 10.0 | Bonus for heading boundaries |
| sentence_end_score_bonus | 6.0 | Bonus for sentence endings |
| sentence_integrity_weight | 8.0 | Weight for sentence boundary detection |
| length_score_factor | 100 | Divisor for accumulated length contribution |
| search_window | 5 | Elements to search for nearby sentence boundary |
| heading_after_penalty | 12.0 | Penalty for splitting right after a heading |
| force_split_before_heading | true | Always split before headings |
| heading_cooldown_elements | 2 | Min elements after heading before allowing split |
| custom_heading_regex | "" | Additional heading patterns (comma-separated) |
