# System Architecture

## Module Dependency Graph

```
app.py (Flask Entry)
├── services/runtime_config.py     [RuntimeConfigProvider]
│   └── services/config_schema.py  [CONFIG_SCHEMA, validate_and_coerce, mask_sensitive]
├── services/task_manager.py       [TaskManager]
│   └── models/task_models.py      [Task, FileState, Event, Stage, enums]
├── services/pipeline_runner.py    [run_pipeline]
│   ├── zotero_client.py           [check_connection, collect_files]
│   ├── mineru_client.py           [process_files]
│   ├── md_cleaner.py              [clean_all]
│   ├── splitter/pipeline.py       [smart_split_all]
│   │   ├── splitter/md_element_extractor.py
│   │   ├── splitter/heading_detector.py
│   │   ├── splitter/sentence_boundary.py  [jieba, nltk]
│   │   ├── splitter/split_scorer.py
│   │   └── splitter/split_renderer.py
│   ├── dify_client.py             [get_or_create_dataset, upload_all]
│   └── progress.py                [load_progress, save_progress]
├── web/routes/health.py           [health_bp]
├── web/routes/config_api.py       [config_bp]
├── web/routes/tasks_api.py        [tasks_bp]
└── web/routes/zotero_api.py       [zotero_bp]
```

## Data Flow

```
Browser
  │
  ▼ POST /api/v1/tasks {collection_keys}
Flask (main thread)
  │
  ├── config_provider.get_snapshot() → cfg dict (frozen for this task)
  ├── task_manager.create_task(keys, cfg, version) → Task object
  └── task_manager.start_task(task_id, run_pipeline)
        │
        ▼ Background Thread
      run_pipeline(task, cancel_event)
        │
        ├── Stage: zotero_collect
        │     check_connection(cfg) → bool
        │     collect_files(cfg, progress, keys) → file_map
        │
        ├── Stage: mineru_upload + mineru_poll
        │     process_files(cfg, file_map) → md_results, failures
        │
        ├── Stage: md_clean
        │     clean_all(md_results, cfg) → cleaned_results, stats
        │
        ├── Stage: smart_split
        │     smart_split_all(md_results, cfg) → split_results, stats
        │     (if smart_split.enabled: force separator = <!--split-->)
        │
        ├── Stage: dify_upload + dify_index
        │     get_or_create_dataset(cfg) → dataset_id
        │     upload_all(cfg, dataset_id, md_results) → uploaded, failed
        │
        └── Stage: finalize
              Update task status, save progress
```

## Config Injection Pattern

All client modules accept `cfg: dict` parameter instead of module-level imports:

```python
def some_function(cfg):
    dify_cfg = cfg.get("dify", {})
    base_url = dify_cfg.get("base_url", "")
    api_key = dify_cfg.get("api_key", "")
    requests.get(f"{base_url}/...", headers={"Authorization": f"Bearer {api_key}"})
```

## Thread Safety

- `RuntimeConfigProvider`: `threading.RLock` protects all reads/writes
- `TaskManager`: `threading.RLock` protects task dict operations
- `Task` object: Mutated only by the owning pipeline thread (single writer)
- `progress.json`: Written atomically via tmp file + `os.replace`
- `config/runtime_config.json`: Written atomically via tmp file + `os.replace`

## Frontend Architecture

Single-page application (SPA) pattern:
- `templates/index.html`: Bootstrap 5 CDN, two views (dashboard/config) toggled via `d-none` class
- `static/js/main.js`: View switching, app initialization
- `static/js/dashboard.js`: Pipeline control, 2s polling, stepper, event log, file status
- `static/js/config.js`: Dynamic form rendering from schema, save/reset/import
- `static/js/api.js`: Centralized API wrapper for all endpoints
- `static/js/utils.js`: Toast notifications, HTML escape, time formatting
