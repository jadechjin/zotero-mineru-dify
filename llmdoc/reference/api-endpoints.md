# REST API Specification

Base URL: `/api/v1`

## Health

### GET /health

Response: `{"status": "ok"}`

## Config

### GET /config

Returns current config with sensitive fields masked (last 4 chars visible).

Response:
```json
{
  "success": true,
  "data": {
    "zotero": { "mcp_url": "http://127.0.0.1:23120/mcp", ... },
    "mineru": { "api_token": "****abcd", ... },
    "dify": { ... },
    "md_clean": { ... },
    "smart_split": { ... }
  },
  "version": 5
}
```

### PUT /config

Partial update. Only provided fields are merged.

Request body:
```json
{
  "dify": { "dataset_name": "My Knowledge Base" }
}
```

Response: Same as GET /config (masked, new version).

### GET /config/schema

Returns the full CONFIG_SCHEMA with field types, defaults, labels, bounds.

### POST /config/import-env

Import from `.env` file using ENV_KEY_MAP.

Request body (optional):
```json
{ "path": ".env" }
```

### POST /config/reset

Reset all config to schema defaults.

## Tasks

### POST /tasks

Create and start a new pipeline task.

Request body:
```json
{
  "collection_keys": ["KEY1", "KEY2"]
}
```

Response (201):
```json
{
  "success": true,
  "task_id": "abc123def456"
}
```

Error (409): Already a task running/queued.

### GET /tasks

List all tasks (summary format).

Response:
```json
{
  "success": true,
  "data": [
    {
      "task_id": "abc123def456",
      "status": "running",
      "stage": "mineru_poll",
      "created_at": 1708000000.0,
      "started_at": 1708000001.0,
      "finished_at": null,
      "collection_keys": ["KEY1"],
      "config_version": 5,
      "error": "",
      "stats": { "total": 10, "succeeded": 3, "failed": 1, "skipped": 0, "pending": 6 }
    }
  ]
}
```

### GET /tasks/:id

Full task detail including file list.

### GET /tasks/:id/events?after_seq=N

Incremental event polling. Returns events with seq > N.

Response:
```json
{
  "success": true,
  "data": [
    {
      "seq": 5,
      "ts": 1708000010.0,
      "level": "info",
      "stage": "mineru_upload",
      "event": "stage_enter",
      "message": "Starting MinerU batch parse"
    }
  ]
}
```

### GET /tasks/:id/files

Per-file status list.

Response:
```json
{
  "success": true,
  "data": [
    {
      "filename": "paper.pdf",
      "status": "succeeded",
      "stage": "dify_upload",
      "error": "",
      "progress": 0.0
    }
  ]
}
```

### POST /tasks/:id/cancel

Cancel a running or queued task.

Response: `{"success": true, "message": "..."}` or 409 if not cancellable.

### POST /tasks/:id/files/:filename/skip

Skip a specific file's subsequent processing in a running task. The file must be in a non-terminal status (not `succeeded`, `failed`, or `skipped`).

The `:filename` path parameter should be URL-encoded if it contains special characters.

**Skip Behavior:**
- Immediately marks the file as `skipped` in the task's file list
- Adds the filename to the shared `skip_files` set
- Pipeline thread checks this set at MD Clean and Dify Upload stage boundaries
- Smart-split child parts (files split from the parent) are also skipped automatically

Response (200):
```json
{ "success": true, "message": "文件已标记为跳过: paper.pdf" }
```

Error (409): File is in terminal status, task not running, or file not found.
```json
{ "success": false, "error": "文件已处于终态: succeeded" }
```

## Zotero

### GET /zotero/health

Check Zotero MCP connection using current config.

Response:
```json
{ "success": true, "connected": true, "message": "Zotero MCP 服务连通" }
```

### GET /zotero/collections

List Zotero collections.

Response:
```json
{
  "success": true,
  "data": [
    { "key": "ABC123", "name": "My Papers", "depth": 0 }
  ]
}
```

## Services

Connectivity tests for external services. All return unified format:

```json
{ "success": true, "connected": true, "message": "描述信息" }
```

### GET /mineru/health

Check MinerU API connectivity and token validity.

### GET /dify/health

Check Dify API connectivity and API key validity.

### GET /image-summary/health

Check vision model API connectivity and API key validity.

## Status Enums

### TaskStatus
`queued` | `running` | `succeeded` | `failed` | `cancelled` | `partial_succeeded`

### Stage
`init` | `zotero_collect` | `mineru_upload` | `mineru_poll` | `md_clean` | `smart_split` | `dify_upload` | `finalize`

### FileStatus
`pending` | `processing` | `succeeded` | `failed` | `skipped`
