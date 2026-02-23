# Contributing Guide

## Project Overview

Zotero-MinerU-Dify Pipeline: Automated pipeline that fetches Zotero PDF attachments, parses them via MinerU to Markdown, applies smart splitting, and uploads to Dify knowledge base for RAG applications.

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Web Framework | Flask 3.0+ |
| Frontend | Vanilla JS + Bootstrap 5 CDN (SPA) |
| Background Tasks | `threading.Thread` (1 concurrent task max) |
| Config Storage | JSON file (atomic write) |
| NLP | jieba (Chinese) + NLTK (English) |
| External APIs | Zotero MCP, MinerU REST, Dify REST |

## Environment Setup

### 1. Clone and install dependencies

```bash
git clone <repo-url>
cd zotero-mineru-dify
pip install -r requirements.txt
```

### 2. Configure environment variables

Copy `.env.example` to `.env` and fill in required values:

```bash
cp .env.example .env
```

#### Required Variables

| Variable | Description |
|----------|-------------|
| `ZOTERO_MCP_URL` | Zotero MCP server address (default: `http://127.0.0.1:23120/mcp`) |
| `MINERU_API_TOKEN` | MinerU API authentication token |
| `DIFY_API_KEY` | Dify Dataset API key |
| `DIFY_BASE_URL` | Dify API base URL (default: `https://api.dify.ai/v1`) |
| `DIFY_DATASET_NAME` | Target Dify knowledge base name (default: `Zotero Literature`) |

#### Optional Variables — Zotero

| Variable | Description |
|----------|-------------|
| `ZOTERO_COLLECTION_KEYS` | Comma-separated collection keys; empty = all library |
| `ZOTERO_COLLECTION_RECURSIVE` | Include sub-collections (default: `true`) |
| `ZOTERO_COLLECTION_PAGE_SIZE` | Pagination size (default: `50`) |

#### Optional Variables — Dify Processing

| Variable | Description |
|----------|-------------|
| `DIFY_PROCESS_MODE` | `custom` or `automatic` (default: `custom`) |
| `DIFY_SEGMENT_SEPARATOR` | Segment separator (default: `\n\n`) |
| `DIFY_SEGMENT_MAX_TOKENS` | Max tokens per segment (default: `800`) |
| `DIFY_REMOVE_EXTRA_SPACES` | Strip extra spaces (default: `true`) |
| `DIFY_REMOVE_URLS_EMAILS` | Strip URLs/emails (default: `false`) |
| `DIFY_DOC_FORM` | Force doc form: `text_model`/`hierarchical_model`; empty = auto |
| `DIFY_DOC_LANGUAGE` | Force doc language; empty = auto |

#### Optional Variables — Markdown Cleaning

| Variable | Description |
|----------|-------------|
| `MD_CLEAN_ENABLED` | Enable cleaning (default: `true`) |
| `MD_CLEAN_COLLAPSE_BLANK_LINES` | Compress 3+ blank lines to 2 (default: `true`) |
| `MD_CLEAN_STRIP_HTML` | Remove residual HTML tags (default: `true`) |
| `MD_CLEAN_REMOVE_CONTROL_CHARS` | Remove invisible control chars (default: `true`) |
| `MD_CLEAN_REMOVE_IMAGE_PLACEHOLDERS` | Remove `![](...)` placeholders (default: `true`) |
| `MD_CLEAN_REMOVE_PAGE_NUMBERS` | Remove standalone page numbers (default: `false`) |
| `MD_CLEAN_REMOVE_WATERMARK` | Remove watermark text (default: `false`) |
| `MD_CLEAN_WATERMARK_PATTERNS` | Watermark regex patterns, comma-separated |

#### Optional Variables — Image Summary (Vision API)

| Variable | Description |
|----------|-------------|
| `IMAGE_SUMMARY_ENABLED` | Enable image summary rewrite (default: `true`) |
| `IMAGE_SUMMARY_PROVIDER` | Vision API provider: `openai` or `newapi` |
| `IMAGE_SUMMARY_API_BASE_URL` | Vision model API base URL |
| `IMAGE_SUMMARY_API_KEY` | Vision model API key |
| `IMAGE_SUMMARY_MODEL` | Vision model name (default: `gpt-4.1-mini`) |
| `IMAGE_SUMMARY_USE_SYSTEM_PROXY` | Follow system proxy settings (default: `true`) |
| `IMAGE_SUMMARY_EXTRA_BODY_JSON` | Extra request body params (JSON string) |
| `IMAGE_SUMMARY_CONCURRENCY` | Image parsing concurrency (default: `4`) |
| `IMAGE_SUMMARY_TIMEOUT_S` | Request timeout in seconds (default: `120`) |
| `IMAGE_SUMMARY_MAX_CONTEXT_CHARS` | Max context chars per image (default: `3000`) |
| `IMAGE_SUMMARY_MAX_IMAGES_PER_DOC` | Max images per document (default: `50`) |
| `IMAGE_SUMMARY_MAX_TOKENS` | Vision model output token limit (default: `900`) |
| `IMAGE_SUMMARY_TEMPERATURE` | Vision model temperature (default: `0.1`) |

#### Optional Variables — Smart Split

| Variable | Description |
|----------|-------------|
| `SMART_SPLIT_ENABLED` | Enable smart splitting (default: `true`) |
| `SMART_SPLIT_STRATEGY` | Strategy: `paragraph_wrap` or `semantic` |
| `SMART_SPLIT_MARKER` | Split marker (default: `<!--split-->`) |

### 3. Import config via Web UI

After starting the app, you can import `.env` values into the runtime config via:
- Web UI: Config page -> "Import from .env" button
- API: `POST /api/v1/config/import-env`

## Running the Application

```bash
python app.py
```

The web UI will be available at `http://127.0.0.1:5000`.

## Project Structure

```
app.py                          # Flask entry point
services/
  runtime_config.py             # RuntimeConfigProvider (JSON persistence)
  config_schema.py              # CONFIG_SCHEMA definition, validation
  task_manager.py               # Thread-safe task lifecycle
  pipeline_runner.py            # Background pipeline execution
models/
  task_models.py                # Task, FileState, Event dataclasses
splitter/
  pipeline.py                   # Smart split orchestrator
  md_element_extractor.py       # Markdown -> MDElement parser
  heading_detector.py           # Heading detection
  sentence_boundary.py          # Sentence boundary (jieba + NLTK)
  split_scorer.py               # Multi-dimensional scoring
  split_renderer.py             # Insert split markers
web/routes/
  health.py                     # GET /api/v1/health
  config_api.py                 # Config CRUD
  tasks_api.py                  # Task management
  zotero_api.py                 # Zotero proxy
  services_api.py               # Service health checks
static/js/
  main.js                       # View switching, init
  dashboard.js                  # Pipeline control, polling, stepper
  config.js                     # Dynamic form, connectivity tests
  api.js                        # Centralized API wrapper
  utils.js                      # Toast, HTML escape, time formatting
templates/
  index.html                    # SPA main page (Bootstrap 5)
zotero_client.py                # Zotero MCP client
mineru_client.py                # MinerU REST client
dify_client.py                  # Dify REST client
md_cleaner.py                   # Markdown cleaning + vision API
```

## Pipeline Stages

```
init -> zotero_collect -> mineru_upload -> mineru_poll -> md_clean -> smart_split -> dify_upload -> finalize
```

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v1/health` | Health check |
| GET | `/api/v1/config` | Get current config (masked) |
| PUT | `/api/v1/config` | Partial config update |
| GET | `/api/v1/config/schema` | Full config schema |
| POST | `/api/v1/config/import-env` | Import from .env |
| POST | `/api/v1/config/reset` | Reset to defaults |
| POST | `/api/v1/tasks` | Create pipeline task |
| GET | `/api/v1/tasks` | List all tasks |
| GET | `/api/v1/tasks/:id` | Task detail |
| GET | `/api/v1/tasks/:id/events` | Incremental event poll |
| GET | `/api/v1/tasks/:id/files` | File status list |
| POST | `/api/v1/tasks/:id/cancel` | Cancel task |
| POST | `/api/v1/tasks/:id/files/:filename/skip` | Skip file |
| GET | `/api/v1/zotero/health` | Zotero connectivity |
| GET | `/api/v1/zotero/collections` | List collections |
| GET | `/api/v1/mineru/health` | MinerU connectivity |
| GET | `/api/v1/dify/health` | Dify connectivity |
| GET | `/api/v1/image-summary/health` | Vision API connectivity |

## Development Notes

- Config changes take effect on the **next** pipeline run (running tasks use a frozen snapshot)
- Maximum 1 concurrent pipeline task
- Frontend uses 2-second polling interval for progress updates
- All client modules use config injection pattern (`cfg: dict` parameter)
