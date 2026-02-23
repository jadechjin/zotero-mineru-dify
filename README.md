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
- **Image Summary Rewrite** — Vision API-powered image description, replacing image placeholders with contextual text summaries
- **Full-chain automation** — From Zotero library to Dify knowledge base with one click
- **Idempotent execution** — Skip logic compares against Dify remote dataset; safe to re-run without duplicates
- **File-level skip** — Skip individual files mid-run from the dashboard without cancelling the entire task
- **Service connectivity testing** — Verify Zotero, MinerU, Dify, and Vision API connections from the config page before running
- **Batch processing** — Processes up to 200 files per MinerU batch
- **Collection filtering** — Target specific Zotero collections with recursive sub-collection support
- **Pipeline file support** — Auto-discover `.pipeline` export files for Dify chunking rules
- **Multiple input formats** — PDF, DOC, DOCX, PPT, PPTX, PNG, JPG, JPEG

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

1. Open `http://127.0.0.1:5000` in your browser
2. Go to **Config** tab — fill in API keys (Zotero MCP URL, MinerU Token, Dify API Key, Dataset Name)
3. Use the **connectivity test** buttons to verify each service connection
4. Adjust smart split, Markdown cleaning, and image summary settings as needed
5. Go to **Dashboard** — enter Zotero collection keys (optional) and click **Start Pipeline**
6. Monitor real-time progress: pipeline stage stepper, event log, per-file status
7. Optionally **skip** individual files mid-run if needed

## Configuration

### Web UI (Recommended)

All settings are editable from the Config page. Changes are saved to `config/runtime_config.json` and take effect on the next pipeline run.

Categories: **Zotero** | **MinerU** | **Dify** | **Markdown Cleaning** | **Image Summary** | **Smart Split**

### Environment Variables

For initial setup or migration, configure via `.env` file. See `.env.example` for a full template. The Web UI can import `.env` settings via the "Import from .env" button.

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
│
├── models/
│   └── task_models.py              # Task, FileState, Event data models
│
├── services/
│   ├── config_schema.py            # Config schema, defaults, validation
│   ├── runtime_config.py           # RuntimeConfigProvider (JSON persistence)
│   ├── task_manager.py             # Task lifecycle management (thread-safe)
│   └── pipeline_runner.py          # Pipeline execution in background thread
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
│   └── routes/
│       ├── health.py               # GET /api/v1/health
│       ├── config_api.py           # Config CRUD API
│       ├── tasks_api.py            # Task management API
│       ├── zotero_api.py           # Zotero proxy API
│       └── services_api.py         # Service health check API
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
├── md_cleaner.py                   # Markdown cleaning + image summary
├── requirements.txt                # Python dependencies
├── .env.example                    # Environment variable template
├── docs/
│   ├── CONTRIB.md                  # Developer contribution guide
│   └── RUNBOOK.md                  # Operations runbook
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
| POST | `/api/v1/tasks/:id/files/:filename/skip` | Skip a file mid-run |
| GET | `/api/v1/zotero/health` | Check Zotero MCP connection |
| GET | `/api/v1/zotero/collections` | List Zotero collections |
| GET | `/api/v1/mineru/health` | Check MinerU API connection |
| GET | `/api/v1/dify/health` | Check Dify API connection |
| GET | `/api/v1/image-summary/health` | Check Vision API connection |

## How It Works

1. **Configure** — Set API keys and preferences via Web UI; verify connections with built-in health checks
2. **Collect** — Queries Zotero via MCP to gather attachment file paths, filtered by collection; skips items already uploaded to Dify (unhealthy docs in Dify are automatically re-processed)
3. **Parse** — Uploads files to MinerU API in batches, polls for completion, downloads Markdown
4. **Clean** — Applies Markdown cleaning rules (strip HTML, collapse blank lines, remove placeholders)
5. **Image Summary** — Replaces image placeholders with AI-generated text descriptions via Vision API
6. **Smart Split** — Analyzes document structure, detects headings and sentence boundaries, scores optimal split points, inserts `<!--split-->` markers
7. **Upload** — Submits documents to Dify; files are considered complete upon successful submission (indexing runs asynchronously in Dify)

## Documentation

- [docs/CONTRIB.md](docs/CONTRIB.md) — Developer contribution guide with full environment variable reference
- [docs/RUNBOOK.md](docs/RUNBOOK.md) — Operations runbook: deployment, monitoring, troubleshooting

## License

MIT
