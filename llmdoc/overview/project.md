# Project Overview

## What Is This

Zotero-MinerU-Dify Pipeline 是一个文献知识库自动化工具，将 Zotero 文献管理器中的 PDF 附件自动解析为 Markdown，经过智能分割处理后上传到 Dify 知识库，用于 RAG（检索增强生成）应用。

## Tech Stack

| Layer | Technology | Notes |
|-------|-----------|-------|
| Web Framework | Flask 3.0+ | Single process + threading |
| Frontend | Vanilla JS + Bootstrap 5 CDN | SPA, no build step |
| Background Tasks | threading.Thread | 1 concurrent task max |
| Config Storage | JSON file | Atomic write (tmp -> os.replace) |
| Skip Logic | Dify remote dataset comparison | Idempotent re-runs |
| External APIs | Zotero MCP, MinerU REST, Dify REST | |
| NLP | jieba (Chinese), NLTK (English) | Sentence boundary detection |

## Design Decisions

### CLI -> Web Migration (v2.0)

Original: CLI tool (`pipeline.py`) with `.env` configuration — **removed in v2.1 dead code cleanup**.

Current: Flask Web application (`app.py`) with:
- **RuntimeConfigProvider** — JSON-persisted config with hot-update semantics
- **TaskManager** — Thread-safe task lifecycle with event stream
- **Polling API** — 2s interval frontend polling (not SSE/WebSocket)
- **Config injection** — All client modules accept `cfg: dict` parameter instead of module-level imports

### Smart Split (VerbaAurea-inspired)

Borrowed from VerbaAurea project's text analysis approach, adapted from DOCX to Markdown:
- Element extraction: Markdown syntax -> MDElement typed dicts
- Heading detection: `#` syntax + configurable regex patterns
- Sentence boundary: jieba (Chinese) + NLTK (English) with lazy loading
- Multi-dimensional scoring: heading bonus, sentence end bonus, integrity weight, length factor
- Split rendering: Insert `<!--split-->` markers at scored split points

### Config Hot-Update Semantics

- New tasks read latest config snapshot at creation time
- Running tasks freeze their config (snapshot bound to task)
- Frontend edits take effect on next pipeline run, not on running tasks

## Entry Points

| Entry | File | Usage |
|-------|------|-------|
| Web UI | `app.py` | `python app.py` -> http://127.0.0.1:5000 |
