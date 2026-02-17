# Zotero-MinerU-Dify Pipeline

[中文文档](README_CN.md)

An automated pipeline that extracts PDF attachments from **Zotero**, parses them into Markdown via **MinerU**, applies **smart splitting**, and uploads the results to a **Dify** knowledge base for RAG applications. Managed through a **Web UI**.

## Architecture

```
                        ┌─────────────────────────────────────────┐
                        │           Flask Web Application          │
                        │  ┌────────────┐  ┌────────────────────┐ │
  Browser ◄────────────►│  │  REST API   │  │  Static Frontend   │ │
  (Dashboard / Config)  │  │  /api/v1/*  │  │  HTML + Vanilla JS │ │
                        │  └─────┬──────┘  └────────────────────┘ │
                        │        │                                 │
                        │  ┌─────▼──────────────────────────────┐ │
                        │  │        Pipeline Runner (Thread)     │ │
                        │  │  Zotero → MinerU → Clean → Split   │ │
                        │  │         → Dify Upload              │ │
                        │  └────────────────────────────────────┘ │
                        │                                         │
                        │  ┌────────────┐  ┌────────────────────┐ │
                        │  │  Runtime    │  │    Task Manager    │ │
                        │  │  Config     │  │  (Event Stream)    │ │
                        │  │  (JSON)     │  │                    │ │
                        │  └────────────┘  └────────────────────┘ │
                        └─────────────────────────────────────────┘
                               │              │             │
                        ┌──────▼──┐   ┌───────▼───┐   ┌────▼─────┐
                        │  Zotero  │   │   MinerU   │   │   Dify   │
                        │  (MCP)   │   │ (Parse API)│   │ (RAG/KB) │
                        └─────────┘   └───────────┘   └──────────┘
```

## Features

- **Web Dashboard** — Real-time pipeline progress per file with polling-based event stream
- **Frontend Config** — Edit all settings (API keys, chunking rules, split params) from the browser, persisted as JSON
- **Smart Splitting** — Semantic-aware Markdown chunking inspired by [VerbaAurea](https://github.com/VerbaAurea/VerbaAurea): heading detection, sentence boundary analysis (jieba + NLTK), multi-dimensional scoring
- **Full-chain automation** — From Zotero library to Dify knowledge base with one click
- **Idempotent execution** — Progress tracking via JSON state file; safe to re-run
- **Batch processing** — Processes up to 200 files per MinerU batch
- **Collection filtering** — Target specific Zotero collections with recursive sub-collection support
- **Pipeline file support** — Auto-discover `.pipeline` export files for Dify chunking rules
- **Multiple input formats** — PDF, DOC, DOCX, PPT, PPTX, PNG, JPG, JPEG
- **Legacy CLI** — `pipeline.py` still available for headless/scripted usage

## Prerequisites

| Dependency | Version | Notes |
|------------|---------|-------|
| Python | 3.10+ | |
| Zotero | 7.0+ | With [zotero-mcp](https://github.com/nicholasgasior/zotero-mcp) plugin running |
| MinerU API Token | - | Register at [mineru.net](https://mineru.net) |
| Dify API Key | - | Dataset API key from your Dify instance |

## Quick Start

```bash
# Clone the repository
git clone https://github.com/jadechjin/zotero-mineru-dify.git
cd zotero-mineru-dify

# Create virtual environment
python -m venv .venv
source .venv/bin/activate   # Linux/macOS
.venv\Scripts\activate      # Windows

# Install dependencies
pip install -r requirements.txt

# (Optional) Import existing .env config on first launch
# The web UI will auto-import .env if config/runtime_config.json doesn't exist

# Start the web application
python app.py
# Open http://127.0.0.1:5000 in your browser
```

## Usage

### Web Interface (Recommended)

1. Open `http://127.0.0.1:5000` in your browser
2. Go to **Config** tab — fill in API keys (Zotero MCP URL, MinerU Token, Dify API Key, Dataset Name)
3. Adjust smart split and Markdown cleaning settings as needed
4. Go to **Dashboard** — enter Zotero collection keys (optional) and click **Start Pipeline**
5. Monitor real-time progress: pipeline stage stepper, event log, per-file status

### Legacy CLI

```bash
# Interactive mode - select collections from a menu
python pipeline.py --interactive

# Process entire Zotero library
python pipeline.py --all-items

# Process specific collections
python pipeline.py --collections KEY1,KEY2

# Disable recursive sub-collection inclusion
python pipeline.py --collections KEY1 --no-recursive

# Custom pagination size
python pipeline.py --all-items --page-size 100
```

## Configuration

### Web UI (Recommended)

All settings are editable from the Config page. Changes are saved to `config/runtime_config.json` and take effect on the next pipeline run.

Categories: **Zotero** | **MinerU** | **Dify** | **Markdown Cleaning** | **Smart Split**

### Environment Variables (Legacy)

For CLI usage, configure via `.env` file. See `.env.example` for a full template. The Web UI can import `.env` settings via the "Import from .env" button.

| Variable | Description | Default |
|----------|-------------|---------|
| `ZOTERO_MCP_URL` | Zotero MCP server address | `http://127.0.0.1:23120/mcp` |
| `MINERU_API_TOKEN` | MinerU API authentication token | - |
| `DIFY_API_KEY` | Dify dataset API key | - |
| `DIFY_BASE_URL` | Dify API base URL | `https://api.dify.ai/v1` |
| `DIFY_DATASET_NAME` | Target knowledge base name | `Zotero Literature` |
| `DIFY_PROCESS_MODE` | Chunking strategy (`custom` / `automatic`) | `custom` |
| `DIFY_SEGMENT_MAX_TOKENS` | Max tokens per chunk | `800` |
| `ZOTERO_COLLECTION_KEYS` | Comma-separated collection keys (optional) | - |

## Project Structure

```
zotero-mineru-dify/
├── app.py                          # Flask entry point (Web UI)
├── pipeline.py                     # Legacy CLI entry point
├── config.py                       # Legacy .env config loader
│
├── models/
│   └── task_models.py              # Task, FileState, Event data models
│
├── services/
│   ├── config_schema.py            # Config schema, defaults, validation
│   ├── runtime_config.py           # RuntimeConfigProvider (JSON persistence)
│   ├── task_manager.py             # Task lifecycle management (thread-safe)
│   ├── pipeline_runner.py          # Pipeline execution in background thread
│   └── event_bus.py                # Event publish/subscribe bus
│
├── splitter/                       # Smart split module (inspired by VerbaAurea)
│   ├── md_element_extractor.py     # Markdown → MDElement[] parser
│   ├── heading_detector.py         # Heading detection (regex + Markdown syntax)
│   ├── sentence_boundary.py        # Sentence boundary (jieba + NLTK)
│   ├── split_scorer.py             # Multi-dimensional scoring system
│   ├── split_renderer.py           # Insert <!--split--> markers
│   └── pipeline.py                 # Orchestrates the 5 sub-modules
│
├── web/
│   ├── errors.py                   # Error response helpers
│   └── routes/
│       ├── health.py               # GET /api/v1/health
│       ├── config_api.py           # Config CRUD API
│       ├── tasks_api.py            # Task management API
│       └── zotero_api.py           # Zotero proxy API
│
├── templates/
│   └── index.html                  # SPA main page (Bootstrap 5)
├── static/
│   ├── css/style.css               # Custom styles
│   └── js/
│       ├── main.js                 # App init + routing
│       ├── dashboard.js            # Dashboard view + polling
│       ├── config.js               # Config editor view
│       ├── api.js                  # API request wrapper
│       └── utils.js                # Toast, helpers
│
├── zotero_client.py                # Zotero MCP client
├── mineru_client.py                # MinerU API client
├── dify_client.py                  # Dify API client
├── md_cleaner.py                   # Markdown cleaning pipeline
├── progress.py                     # JSON-based progress tracking
├── requirements.txt                # Python dependencies
├── .env.example                    # Environment variable template
└── config/
    └── runtime_config.json         # Runtime config (auto-generated)
```

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v1/health` | Health check |
| GET | `/api/v1/config` | Get current config (masked) |
| PUT | `/api/v1/config` | Update config |
| GET | `/api/v1/config/schema` | Get config schema |
| POST | `/api/v1/config/import-env` | Import from .env file |
| POST | `/api/v1/config/reset` | Reset to defaults |
| POST | `/api/v1/tasks` | Create pipeline task |
| GET | `/api/v1/tasks` | List all tasks |
| GET | `/api/v1/tasks/:id` | Get task details |
| GET | `/api/v1/tasks/:id/events?after_seq=N` | Get incremental events |
| GET | `/api/v1/tasks/:id/files` | Get per-file status |
| POST | `/api/v1/tasks/:id/cancel` | Cancel a running task |
| GET | `/api/v1/zotero/health` | Check Zotero MCP connection |
| GET | `/api/v1/zotero/collections` | List Zotero collections |

## How It Works

1. **Configure** — Set API keys and preferences via Web UI (or `.env` for CLI)
2. **Collect** — Queries Zotero via MCP to gather attachment file paths, filtered by collection
3. **Parse** — Uploads files to MinerU API in batches, polls for completion, downloads Markdown
4. **Clean** — Applies Markdown cleaning rules (strip HTML, collapse blank lines, remove placeholders)
5. **Smart Split** — Analyzes document structure, detects headings and sentence boundaries, scores optimal split points, inserts `<!--split-->` markers
6. **Upload** — Creates documents in Dify with chunking rules aligned to split markers
7. **Track** — Records processed/failed items in `progress.json`; subsequent runs skip completed files

## License

MIT
