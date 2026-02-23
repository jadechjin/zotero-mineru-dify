# Runbook

## Deployment

### Prerequisites

- Python 3.10+
- pip
- Running Zotero with [Zotero MCP plugin](https://github.com/) enabled
- MinerU API account with valid token
- Dify instance with Dataset API key

### Install

```bash
pip install -r requirements.txt
```

Dependencies:
- `requests>=2.28.0`
- `python-dotenv>=1.0.0`
- `PyYAML>=6.0.0`
- `flask>=3.0.0`
- `jieba>=0.42.1`
- `nltk>=3.8.0`

### Configure

1. Copy `.env.example` to `.env`
2. Fill in required variables: `ZOTERO_MCP_URL`, `MINERU_API_TOKEN`, `DIFY_API_KEY`, `DIFY_BASE_URL`
3. Start the app and import env via Web UI or API

### Start

```bash
python app.py
```

Default: `http://0.0.0.0:5000`

### Production Considerations

- Flask development server is used by default; for production, use Gunicorn:
  ```bash
  gunicorn -w 1 -b 0.0.0.0:5000 "app:create_app()"
  ```
  **Note**: Must use `-w 1` (single worker) because the app uses in-process threading for task management
- Config file is stored at `config/runtime_config.json` — ensure the directory is writable
- Consider setting `debug=False` in production

## Monitoring

### Health Checks

Verify all external services before running a pipeline:

| Service | Endpoint | What it checks |
|---------|----------|----------------|
| App | `GET /api/v1/health` | Flask process alive |
| Zotero | `GET /api/v1/zotero/health` | MCP server connection |
| MinerU | `GET /api/v1/mineru/health` | API token and connectivity |
| Dify | `GET /api/v1/dify/health` | API key and connectivity |
| Vision | `GET /api/v1/image-summary/health` | Vision model API |

### Task Monitoring

- `GET /api/v1/tasks` — list all tasks with status/stage/stats
- `GET /api/v1/tasks/:id/events?after_seq=N` — incremental event log
- `GET /api/v1/tasks/:id/files` — per-file status

### Key Metrics to Watch

- Task status transitions: `queued -> running -> succeeded/failed/partial_succeeded`
- File-level failures (check `stats.failed` count)
- Unhealthy docs count in event log (`unhealthy_docs_skipped` event)

## Common Issues and Fixes

### Zotero MCP connection refused

**Symptom**: `GET /api/v1/zotero/health` returns `connected: false`

**Fix**:
1. Ensure Zotero desktop app is running
2. Verify MCP plugin is installed and enabled
3. Check `ZOTERO_MCP_URL` matches the MCP server address (default: `http://127.0.0.1:23120/mcp`)

### MinerU API timeout

**Symptom**: Task stuck at `mineru_poll` stage

**Fix**:
1. Check MinerU API status
2. Increase `mineru.poll_timeout_s` in config (default: 7200s = 2h)
3. Large batch jobs may take longer; monitor via task events

### Dify upload failures

**Symptom**: Files show `failed` status at `dify_upload` stage

**Fix**:
1. Verify Dify API key and base URL via `GET /api/v1/dify/health`
2. Check Dify instance rate limits
3. Increase `dify.upload_delay` to reduce request frequency
4. Check Dify dataset document limit

### Dify documents stuck in error/disabled state

**Symptom**: Previously uploaded files are not re-processed on re-runs

**Fix**: Since v2.3.2, documents with `indexing_status=error` or `enabled=false` are automatically excluded from the skip index. Re-running the pipeline will re-process these items.

### Task stuck / not completing

**Symptom**: Task stays in `running` state indefinitely

**Fix**:
1. Cancel the task via `POST /api/v1/tasks/:id/cancel`
2. Check event log for the last stage and any error messages
3. A new task cannot start while the current one is running (max 1 concurrent)

### Config changes not taking effect

**Symptom**: Pipeline uses old configuration values

**Explanation**: Running tasks use a frozen config snapshot taken at creation time. Config changes only apply to the **next** task.

**Fix**: Cancel the current task, update config, then start a new task.

### File-level skip

**Usage**: During a running task, skip individual files via:
- Dashboard: Click "Skip" button on a non-terminal file
- API: `POST /api/v1/tasks/:id/files/:filename/skip`

Skipped files (and their smart-split child parts) are excluded from MD Clean and Dify Upload stages.

## Rollback Procedure

### Config Rollback

The runtime config is stored in `config/runtime_config.json`. To rollback:

1. Stop the application
2. Replace `config/runtime_config.json` with a known-good backup
3. Restart the application

Or use the API:
- `POST /api/v1/config/reset` — reset all config to schema defaults
- `POST /api/v1/config/import-env` — re-import from `.env` file

### Code Rollback

```bash
git log --oneline -10    # find the target commit
git revert <commit-sha>  # create a revert commit
```

## Architecture Notes

- **Single-process**: Flask + threading (no Celery/Redis needed)
- **Config injection**: All modules receive `cfg: dict` parameter, no global state
- **Atomic config writes**: Uses `tmp file + os.replace` pattern
- **Thread safety**: `threading.RLock` for config and task manager; CPython GIL for shared sets
- **Idempotent re-runs**: Skip logic compares against Dify remote dataset (no local progress file)
