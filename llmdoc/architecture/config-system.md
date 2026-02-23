# Config System Architecture

## Overview

The config system replaces `.env` file configuration with a JSON-persisted, frontend-editable runtime configuration provider.

## Components

### CONFIG_SCHEMA (`services/config_schema.py`)

Defines 5 categories with ~31 fields total:

| Category | Key Fields |
|----------|-----------|
| `zotero` | mcp_url, collection_keys, collection_recursive, collection_page_size |
| `mineru` | api_token, poll_timeout_s |
| `dify` | api_key, base_url, dataset_name, pipeline_file, process_mode, segment_separator, segment_max_tokens, chunk_overlap, parent_mode, subchunk_*, remove_*, doc_form, doc_language, upload_delay |
| `md_clean` | enabled, collapse_blank_lines, strip_html, remove_control_chars, remove_image_placeholders, remove_page_numbers, remove_watermark, watermark_patterns |
| `smart_split` | enabled, split_marker, max_length, min_length, min_split_score, heading_score_bonus, sentence_end_score_bonus, sentence_integrity_weight, length_score_factor, search_window, heading_after_penalty, force_split_before_heading, heading_cooldown_elements, custom_heading_regex |

Each field spec: `{type, default, label, sensitive, [min, max, options]}`

### RuntimeConfigProvider (`services/runtime_config.py`)

```python
class RuntimeConfigProvider:
    def __init__(self, config_path=None)  # Default: config/runtime_config.json
    def get_snapshot() -> dict             # Deep copy of current config
    def get_version() -> int               # Monotonically increasing version
    def update(patch: dict) -> dict        # Merge patch, validate, save, return masked
    def import_env(env_path=".env") -> dict # Import .env via ENV_KEY_MAP
    def get_masked() -> dict               # Sensitive fields show last 4 chars
    def reset_to_defaults() -> dict        # Reset to schema defaults
```

Key behaviors:
- **Atomic write**: `tmp_file -> os.replace(tmp, target)` for crash safety
- **Thread-safe**: `threading.RLock` protects all operations
- **Version tracking**: Incremented on every write, used for optimistic concurrency
- **Validation**: `validate_and_coerce()` clamps values to schema bounds
- **Auto .env import**: On first load, if JSON doesn't exist and `.env` is present

### ENV_KEY_MAP (`services/config_schema.py`)

Maps 35 `.env` variable names to `(category, key)` tuples for import:

```python
ENV_KEY_MAP = {
    "DIFY_API_KEY": ("dify", "api_key"),
    "DIFY_BASE_URL": ("dify", "base_url"),
    # ... 30 more mappings
}
```

## Hot-Update Semantics

```
Timeline:
  t0: User edits config in Web UI → config v5 saved
  t1: User starts task → task binds cfg snapshot (v5)
  t2: User edits config again → config v6 saved
  t3: Running task still uses v5 snapshot (frozen)
  t4: Next task starts → uses v6
```
