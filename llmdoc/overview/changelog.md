# Architecture Change Log

## Docs — Generated CONTRIB.md and RUNBOOK.md (2026-02-23)

### Summary

Generated `docs/CONTRIB.md` (development workflow, environment variables, API reference) and `docs/RUNBOOK.md` (deployment, monitoring, troubleshooting, rollback) from project data sources (`.env.example`, `requirements.txt`, `app.py`, `llmdoc/`).

### New Files

| File | Purpose |
|------|---------|
| `docs/CONTRIB.md` | Developer contribution guide with full env var reference |
| `docs/RUNBOOK.md` | Operations runbook with health checks and common fixes |

---

## v2.3 — Dify Upload Simplification + File-Level Skip + Unhealthy Doc Filter (2026-02-22/23)

### v2.3.2 — Unhealthy Document Filter in Skip Logic (2026-02-23)

#### Summary

Fixed an overly aggressive skip logic in `dify_client.get_dataset_document_name_index()` that treated all documents in Dify as "uploaded" regardless of their health status. Documents with `indexing_status == "error"` or `enabled == false` are now excluded from the uploaded index, so that their corresponding Zotero items will be re-collected and re-processed on the next pipeline run.

#### Rationale

- **Problem**: When building the uploaded-document index, the function did not inspect `indexing_status` or `enabled` fields. Dify documents that had failed indexing (error) or were manually disabled were still counted as "already uploaded", causing the pipeline to skip those Zotero items permanently.
- **Fix**: Added two guard conditions in the per-document loop. Documents failing either check are excluded from the `names` and `prefixed_item_keys` sets, and a new `skipped_unhealthy` counter tracks how many were excluded.
- **Observability**: The pipeline runner now emits an `unhealthy_docs_skipped` event during `zotero_collect` so the frontend dashboard can display how many unhealthy docs were detected.

#### Changes

| File | Change |
|------|--------|
| `dify_client.py` | `get_dataset_document_name_index()`: added `indexing_status == "error"` check, `enabled == false` check, `skipped_unhealthy` counter, and new return field `skipped_unhealthy` |
| `services/pipeline_runner.py` | `run_pipeline()` zotero_collect stage: reads `skipped_unhealthy` from remote name index and emits `unhealthy_docs_skipped` event when > 0 |

#### Behavior Change

| Before | After |
|--------|-------|
| All Dify documents (any status) counted as "uploaded" | Only documents with `indexing_status != "error"` AND `enabled == true` counted as "uploaded" |
| Error/disabled docs permanently blocked re-processing | Error/disabled docs are re-collected and re-processed on next run |
| No visibility into unhealthy doc count | Dashboard event log shows count of skipped unhealthy docs |

#### Verified Outcomes

- [OK-1] Documents with `indexing_status=error` are excluded from uploaded index
- [OK-2] Documents with `enabled=false` are excluded from uploaded index
- [OK-3] Healthy documents (`indexing_status != error` and `enabled == true`) are still correctly included
- [OK-4] `skipped_unhealthy` count is returned and logged
- [OK-5] Pipeline event log shows `unhealthy_docs_skipped` event when applicable
- [OK-6] Re-running pipeline re-processes items whose Dify docs were in error/disabled state

---

### v2.3.1 — File-Level Skip (2026-02-23)

#### Summary

Added the ability to skip individual files during a running pipeline task. Users can click a "Skip" button on any non-terminal file in the dashboard, and the file (including its smart-split child parts) will be excluded from subsequent MD Clean and Dify Upload stages.

#### Rationale

- **Granular Control**: Users may want to exclude specific files mid-run (e.g., corrupted PDFs, irrelevant attachments) without cancelling the entire task
- **Non-Blocking**: Skip is immediate; the pipeline thread checks the shared skip set at each stage boundary
- **Consistent Pattern**: Follows the existing `cancel_task()` shared-flag pattern for thread-safe cross-thread communication

#### Changes

##### Backend Changes

| File | Change |
|------|--------|
| `services/task_manager.py` | Added `_skip_files: dict[str, set[str]]` shared collection; new `skip_file(task_id, filename)` method that marks `FileState.status = SKIPPED` and adds filename to the skip set |
| `models/task_models.py` | `summary()` now includes `skipped` count in stats; `pending` calculation subtracts skipped files |
| `web/routes/tasks_api.py` | New endpoint `POST /tasks/<task_id>/files/<filename>/skip` |
| `services/pipeline_runner.py` | `run_pipeline` signature extended with `skip_files: set` parameter; filters skipped files before MD Clean stage; filters skipped files (including split child parts via `_resolve_parent_task_key`) before Dify Upload stage; `_on_dify_progress` ignores events for skipped files |

##### Frontend Changes

| File | Change |
|------|--------|
| `static/js/api.js` | New method `skipFile(taskId, filename)` calling `POST /tasks/{id}/files/{filename}/skip` |
| `static/js/dashboard.js` | File cards show "Skip" button for running tasks with non-terminal file status; `_taskRunning` state tracking; `skipFile()` async method |
| `templates/index.html` | Stats cards expanded from 3 columns (`col-md-4`) to 4 columns (`col-md-3`); new "Skipped" stat card |

##### Thread Safety

- `_skip_files` set is written by the API thread (via `skip_file()`) and read by the pipeline thread (at stage boundaries)
- Thread safety is guaranteed by CPython GIL for `set.add()` and `in` operations
- Follows the same pattern as `_cancel_flags` (`threading.Event`)

#### Verified Outcomes

- [OK-1] Skip button appears only for running tasks on non-terminal files (pending/processing)
- [OK-2] Skipped files are immediately marked SKIPPED in the file list
- [OK-3] Skipped files are excluded from MD Clean processing
- [OK-4] Skipped files and their split child parts are excluded from Dify Upload
- [OK-5] Stats card shows correct skipped count
- [OK-6] Pipeline correctly handles edge case where all remaining files are skipped
- [OK-7] Dify progress callback ignores events for skipped files

---

### v2.3.0 — Dify Upload Flow Simplification (2026-02-22)

### Summary

Simplification of Dify upload pipeline to remove entry indexing polling. Files are considered complete upon successful submission to Dify, eliminating the `wait_for_indexing()` blocking phase. This streamlines the user experience by providing immediate upload confirmation without waiting for Dify's background indexing to complete. `progress.json` persistence has been removed; skip logic now compares against the Dify remote dataset directly.

### Rationale

- **User Intent**: Users want immediate feedback after file upload succeeds, not to wait for indexing
- **Skip Logic**: Re-run deduplication is now driven by live Dify remote state (`uploaded_item_keys`) instead of a local progress file
- **Pipeline Simplification**: `Stage.DIFY_INDEX` removed from the Stage enum; pipeline terminates after `dify_upload` then `finalize`

### Changes

#### Backend Changes

| File | Change |
|------|--------|
| `dify_client.py` | Removed `wait_for_indexing()` function and `POLL_INTERVAL_DIFY` constant; `upload_all()` now returns `uploaded` (submit_ok keys) and `failed` (submit_failed keys) immediately |
| `models/task_models.py` | Removed `Stage.DIFY_INDEX` from Stage enum; new enum: `INIT, ZOTERO_COLLECT, MINERU_UPLOAD, MINERU_POLL, MD_CLEAN, SMART_SPLIT, DIFY_UPLOAD, FINALIZE` |
| `zotero_client.py` | `collect_files()` signature changed: `progress_processed=None, target_dataset=None` replaced by `uploaded_item_keys=None` (`set[str]`); skips items already present in Dify remote dataset |
| `progress.py` | **Deleted** — progress.json persistence no longer used |
| `services/pipeline_runner.py` | Removed all progress.json read/write calls; removed three progress coordination helper functions; removed `index_*` event branches from `_on_dify_progress`; `collect_files` call updated to new signature; `finalize` stage logs Dify console hint |
| `services/config_schema.py` | Removed `index_max_wait_s` field definition and its ENV_KEY_MAP entry |

#### Frontend Changes

| File | Change |
|------|--------|
| `static/js/dashboard.js` | Removed `dify_index` stage from stepper and all index-related progress hints |
| `templates/index.html` | Removed `dify_index` step from stepper UI |

#### Documentation Updates

| File | Change |
|------|--------|
| `llmdoc/architecture/system.md` | Updated pipeline stages flow diagram; updated Data Flow section; removed `progress.py` from module dependency graph; updated skip logic description |
| `llmdoc/reference/api-endpoints.md` | Removed `dify_index` from Stage enum; updated file status example |
| `llmdoc/reference/config-schema.md` | Removed `index_max_wait_s` field; updated ENV_KEY_MAP count |

### Verified Outcomes

- [OK-1] File upload to Dify (submit_ok) immediately shows success status on frontend without waiting for indexing
- [OK-2] Failed uploads (submit_failed) immediately show failure status with reason
- [OK-3] All files upload completion triggers finalize and task ends without blocking on indexing
- [OK-5] Frontend stepper no longer displays `dify_index` step
- [OK-6] Re-running pipeline correctly skips already uploaded files via Dify remote comparison
- [OK-7] Partial upload failures result in `partial_succeeded` status; failed files can retry on next run
- [OK-8] Pipeline end event log includes hint: "Files submitted to Dify. Check indexing status in Dify console"

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
