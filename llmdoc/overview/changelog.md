# Architecture Change Log

## v2.3 — Dify Upload Flow Simplification (Planned)

### Summary

Simplification of Dify upload pipeline to remove entry indexing polling. Files are considered complete upon successful submission to Dify, eliminating the `wait_for_indexing()` blocking phase. This streamlines the user experience by providing immediate upload confirmation without waiting for Dify's background indexing to complete.

### Rationale

- **User Intent**: Users want immediate feedback after file upload succeeds, not to wait for indexing
- **Progress Semantics**: `progress["processed"]` changes from "indexed in Dify" to "uploaded to Dify"
- **Pipeline Simplification**: Removes `dify_index` stage or converts it to no-op; pipeline terminates after `dify_upload`

### Planned Changes

#### Backend Changes

| File | Change |
|------|--------|
| `dify_client.py` | Remove `wait_for_indexing()` call from `upload_all()` |
| `services/pipeline_runner.py` | Remove/simplify `dify_index` stage; update progress callbacks to remove `index_*` events |
| `models/task_models.py` | Decide on `Stage.DIFY_INDEX` retention (keep as no-op or remove) |

#### Frontend Changes

| File | Change |
|------|--------|
| `static/js/dashboard.js` | Remove `dify_index` from stepper; remove index-related progress hints |
| `templates/index.html` | Remove `dify_index` step from stepper UI |

#### Documentation Updates

| File | Change |
|------|--------|
| `llmdoc/architecture/system.md` | Update pipeline stages flow diagram; update Data Flow section |
| `llmdoc/reference/api-endpoints.md` | Update Stage enum documentation |

### Success Criteria

- [OK-1] File upload to Dify (submit_ok) immediately shows success status on frontend without waiting for indexing
- [OK-2] Failed uploads (submit_failed) immediately show failure status with reason
- [OK-3] All files upload completion triggers finalize and task ends without blocking on indexing
- [OK-4] `progress.json` `processed` field records timestamp upon upload success (not indexing completion)
- [OK-5] Frontend stepper no longer displays `dify_index` step
- [OK-6] Re-running pipeline correctly skips already uploaded files
- [OK-7] Partial upload failures result in `partial_succeeded` status; failed files can retry on next run
- [OK-8] Pipeline end event log includes hint: "Files submitted to Dify. Check indexing status in Dify console"

### Research Reference

Team research document: `.claude/team-plan/dify-upload-ux-research.md`

---

## v2.2 — Service Connectivity Testing (2026-02-21)

### Summary

Added connectivity testing for all 4 external services (Zotero, MinerU, Dify, Vision Model API). Users can now verify service configuration directly from the config page before running the pipeline.

### New Files

| File | Purpose |
|------|---------|
| `web/routes/services_api.py` | Blueprint with 3 health check endpoints (MinerU, Dify, Image Summary) |

### New Functions

| File | Function | Purpose |
|------|----------|---------|
| `mineru_client.py` | `check_connection(cfg)` | Empty batch request to verify token and connectivity |
| `dify_client.py` | `check_connection(cfg)` | `GET /datasets?limit=1` to verify API key and connectivity |
| `md_cleaner.py` | `check_vision_connection(cfg)` | `GET /models` with chat completion fallback |
| `md_cleaner.py` | `_check_vision_via_chat()` | Minimal chat completion for providers without /models |

### API Changes

- New: `GET /api/v1/mineru/health`, `GET /api/v1/dify/health`, `GET /api/v1/image-summary/health`
- Updated: `GET /api/v1/zotero/health` now includes `message` field
- Unified response format: `{"success": true, "connected": bool, "message": str}`

### Frontend Changes

- `static/js/api.js`: Added `checkMinerU()`, `checkDify()`, `checkImageSummary()` methods
- `static/js/config.js`: Added connectivity test buttons in config panels for zotero/mineru/dify/image_summary categories

### Security Fix

- `config/runtime_config.json` removed from git tracking and added to `.gitignore`

## v2.1 — Dead Code Cleanup (2026-02-19)

### Summary

Comprehensive dead code analysis and cleanup. Removed legacy CLI entry point, unused modules, and dead symbols across 8 files.

### Deleted Files

| File | Reason |
|------|--------|
| `pipeline.py` | Legacy CLI entry point, fully replaced by `app.py` + `services/pipeline_runner.py`. Contained 7 duplicate helper functions. |
| `config.py` | Legacy `.env` config module, only imported by `pipeline.py`. Superseded by `services/runtime_config.py` + `services/config_schema.py`. |
| `services/event_bus.py` | `EventBus` class never imported or instantiated by any code. |

### Dead Code Removed

| File | Symbol | Reason |
|------|--------|--------|
| `services/task_manager.py` | `FileState`, `FileStatus`, `Stage` imports | Imported but never used in module |
| `services/runtime_config.py` | `from pathlib import Path` | Imported but never used |
| `mineru_client.py` | `MINERU_MODEL_VERSION = "vlm"` | Constant defined but never referenced (actual value read from `cfg` dict) |
| `dify_client.py` | `get_dataset_doc_form()` | Function never called by any code |
| `models/task_models.py` | `STAGE_ORDER = list(Stage)` | Variable never referenced |
| `web/errors.py` | `server_error()` | Function never called |

### Analysis Tools Used

- `autoflake` — unused imports/variables detection
- `vulture` — dead code detection
- Codex model — cross-reference analysis, false positive filtering
- Manual grep verification for dynamic references (Flask routes, TypedDict fields)

## v2.0 — CLI to Flask Web Application (2026-02-17)

### Summary

Major refactoring from CLI-only tool to Flask Web application with frontend-editable configuration, real-time progress dashboard, and smart splitting pipeline.

### Changes

#### New Modules

| Module | Purpose |
|--------|---------|
| `app.py` | Flask entry point, creates app with all blueprints |
| `services/config_schema.py` | CONFIG_SCHEMA (5 categories, ~32 fields), ENV_KEY_MAP, validation |
| `services/runtime_config.py` | RuntimeConfigProvider — JSON persistence, atomic write, .env import |
| `services/task_manager.py` | Thread-safe task lifecycle, max_concurrent=1 |
| `services/pipeline_runner.py` | Background thread pipeline execution |
| `models/task_models.py` | Task, FileState, Event dataclasses with enums |
| `splitter/md_element_extractor.py` | Markdown -> MDElement[] parser |
| `splitter/heading_detector.py` | Heading detection (regex + Markdown syntax) |
| `splitter/sentence_boundary.py` | Sentence boundary (jieba + NLTK, lazy load) |
| `splitter/split_scorer.py` | Multi-dimensional scoring system |
| `splitter/split_renderer.py` | Insert split markers into Markdown |
| `splitter/pipeline.py` | Orchestrates 5 sub-modules |
| `web/errors.py` | Error response utilities |
| `web/routes/health.py` | Health check endpoint |
| `web/routes/config_api.py` | Config CRUD API |
| `web/routes/tasks_api.py` | Task management API |
| `web/routes/zotero_api.py` | Zotero proxy API |
| `templates/index.html` | SPA main page (Bootstrap 5) |
| `static/css/style.css` | Custom CSS |
| `static/js/*.js` | Frontend JS (main, dashboard, config, api, utils) |

#### Modified Modules (Config Injection)

All client modules refactored from `from config import CONST` to `cfg: dict` parameter injection:

- `dify_client.py` — All 18 DIFY_* constants replaced with `cfg["dify"]` reads
- `zotero_client.py` — MCP URL from `cfg["zotero"]["mcp_url"]`
- `mineru_client.py` — API token/timeout from `cfg["mineru"]`
- `md_cleaner.py` — Clean rules from `cfg["md_clean"]`
- `progress.py` — Progress file path parameterized

#### Pipeline Stages

```
init -> zotero_collect -> mineru_upload -> mineru_poll -> md_clean -> smart_split -> dify_upload -> dify_index -> finalize
```

#### Task State Machine

```
queued -> running -> succeeded | failed | cancelled | partial_succeeded
```

### Dependencies Added

- `flask>=3.0.0`
- `jieba>=0.42.1`
- `nltk>=3.8.0`
