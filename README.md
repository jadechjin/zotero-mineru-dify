# Zotero-MinerU-Dify Pipeline

[中文文档](README_CN.md)

An automated pipeline that extracts PDF attachments from **Zotero**, parses them into Markdown via **MinerU**, and uploads the results to a **Dify** knowledge base for RAG applications.

## Architecture

```
┌──────────────┐       ┌──────────────┐       ┌──────────────┐
│              │       │              │       │              │
│    Zotero    │──────>│    MinerU    │──────>│     Dify     │
│  (Local DB)  │  MCP  │  (Parse API) │  HTTP │  (RAG / KB)  │
│              │       │              │       │              │
└──────────────┘       └──────────────┘       └──────────────┘
  PDF / DOCX / ...       -> Markdown            Knowledge Base
```

## Features

- **Full-chain automation** - From Zotero library to Dify knowledge base in one command
- **Idempotent execution** - Progress tracking via JSON state file; safe to re-run
- **Batch processing** - Processes up to 200 files per MinerU batch
- **Collection filtering** - Target specific Zotero collections with recursive sub-collection support
- **Automatic retry** - Exponential backoff for transient network errors
- **Multiple input formats** - PDF, DOC, DOCX, PPT, PPTX, PNG, JPG, JPEG

## Prerequisites

| Dependency | Version | Notes |
|------------|---------|-------|
| Python | 3.8+ | |
| Zotero | 7.0+ | With [zotero-mcp](https://github.com/nicholasgasior/zotero-mcp) plugin running |
| MinerU API Token | - | Register at [mineru.net](https://mineru.net) |
| Dify API Key | - | Dataset API key from your Dify instance |

## Quick Start

```bash
# Clone the repository
git clone https://github.com/<your-username>/zotero-mineru-dify.git
cd zotero-mineru-dify

# Create virtual environment
python -m venv .venv
source .venv/bin/activate   # Linux/macOS
.venv\Scripts\activate      # Windows

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env with your API keys and preferences

# Run the pipeline
python pipeline.py
```

## Usage

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

All settings are managed through the `.env` file. See `.env.example` for a full template.

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
| `ZOTERO_COLLECTION_RECURSIVE` | Include sub-collections | `true` |

## Project Structure

```
zotero-mineru-dify/
├── pipeline.py          # Main entry point, orchestrates the workflow
├── config.py            # Centralized configuration from environment
├── zotero_client.py     # Zotero MCP client (collections, attachments)
├── mineru_client.py     # MinerU API client (upload, parse, download)
├── dify_client.py       # Dify API client (dataset, document, indexing)
├── progress.py          # JSON-based progress tracking
├── requirements.txt     # Python dependencies
├── .env.example         # Environment variable template
└── progress.json        # Runtime state (auto-generated)
```

## How It Works

1. **Collect** - Queries Zotero via MCP to gather attachment file paths, filtered by collection if specified
2. **Parse** - Uploads files to MinerU API in batches, polls for completion, and downloads the resulting Markdown
3. **Upload** - Creates documents in the target Dify knowledge base with configurable chunking rules
4. **Track** - Records processed/failed items in `progress.json` so subsequent runs skip completed files

## License

MIT
