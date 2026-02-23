# System Architecture

## Module Dependency Graph

```
app.py (Flask Entry)
├── services/runtime_config.py     [RuntimeConfigProvider]
│   └── services/config_schema.py  [CONFIG_SCHEMA, validate_and_coerce, mask_sensitive]
├── services/task_manager.py       [TaskManager: cancel_task, skip_file]
│   └── models/task_models.py      [Task, FileState, Event, Stage, enums]
├── services/pipeline_runner.py    [run_pipeline]
│   ├── zotero_client.py           [check_connection, collect_files]
│   ├── mineru_client.py           [check_connection, process_files]
│   ├── md_cleaner.py              [clean_all, check_vision_connection]
│   ├── splitter/pipeline.py       [smart_split_all]
│   │   ├── splitter/md_element_extractor.py
│   │   ├── splitter/heading_detector.py
│   │   ├── splitter/sentence_boundary.py  [jieba, nltk]
│   │   ├── splitter/split_scorer.py
│   │   └── splitter/split_renderer.py
│   ├── dify_client.py             [check_connection, get_or_create_dataset, get_dataset_document_name_index, upload_all]
├── web/routes/health.py           [health_bp]
├── web/routes/config_api.py       [config_bp]
├── web/routes/tasks_api.py        [tasks_bp]
├── web/routes/zotero_api.py       [zotero_bp]
└── web/routes/services_api.py    [services_bp: mineru/dify/image-summary health]
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
      run_pipeline(task, cancel_event, skip_files)
        │
        ├── Stage: zotero_collect
        │     check_connection(cfg) → bool
        │     collect_files(cfg, keys, uploaded_item_keys) → file_map
        │     (skips items already uploaded; only healthy docs in Dify
        │      are counted — error/disabled docs are excluded so their
        │      items get re-collected and re-processed)
        │
        ├── Stage: mineru_upload + mineru_poll
        │     process_files(cfg, file_map) → md_results, failures
        │
        ├── Stage: md_clean
        │     *** Filter: remove files in skip_files set ***
        │     clean_all(md_results, cfg) → cleaned_results, stats
        │
        ├── Stage: smart_split
        │     smart_split_all(md_results, cfg) → split_results, stats
        │     (if smart_split.enabled: force separator = <!--split-->)
        │
        ├── Stage: dify_upload
        │     *** Filter: remove files in skip_files set (incl. split child parts) ***
        │     get_or_create_dataset(cfg) → dataset_id
        │     upload_all(cfg, dataset_id, md_results) → uploaded, failed
        │     (uploaded = submit_ok keys; failed = submit_failed keys)
        │
        └── Stage: finalize
              Update task status; hint: check indexing in Dify console
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
- `TaskManager`: `threading.RLock` protects task dict operations; `_skip_files` sets shared between API thread (writer) and pipeline thread (reader), safe under CPython GIL
- `Task` object: Mutated only by the owning pipeline thread (single writer)
- `config/runtime_config.json`: Written atomically via tmp file + `os.replace`
- `cancel_event`: `threading.Event` for cross-thread cancellation signaling
- `skip_files`: `set[str]` shared reference; API thread calls `set.add()`, pipeline thread checks `in` — both are atomic under CPython GIL

## Frontend Architecture

Single-page application (SPA) pattern:
- `templates/index.html`: Bootstrap 5 CDN, two views (dashboard/config) toggled via `d-none` class
- `static/js/main.js`: View switching, app initialization
- `static/js/dashboard.js`: Pipeline control, 2s polling, stepper, event log, file status
- `static/js/config.js`: Dynamic form rendering from schema, save/reset/import, connectivity test buttons
- `static/js/api.js`: Centralized API wrapper for all endpoints (config, tasks, zotero, service health checks)
- `static/js/utils.js`: Toast notifications, HTML escape, time formatting
