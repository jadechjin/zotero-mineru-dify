"""配置 schema 定义与校验。"""

CONFIG_SCHEMA = {
    "zotero": {
        "mcp_url": {"type": "str", "default": "http://127.0.0.1:23120/mcp", "label": "MCP 连接地址", "sensitive": False},
        "collection_keys": {"type": "str", "default": "", "label": "分组 Key（逗号分隔）", "sensitive": False},
        "collection_recursive": {"type": "bool", "default": True, "label": "递归子分组", "sensitive": False},
        "collection_page_size": {"type": "int", "default": 50, "min": 1, "max": 500, "label": "分页大小", "sensitive": False},
    },
    "mineru": {
        "api_token": {"type": "str", "default": "", "label": "API Token", "sensitive": True},
        "model_version": {"type": "select", "default": "vlm", "options": ["vlm", "doc"], "label": "解析模型版本", "sensitive": False},
        "poll_timeout_s": {"type": "int", "default": 7200, "min": 60, "max": 86400, "label": "轮询超时（秒）", "sensitive": False},
        "asset_output_dir": {"type": "str", "default": "outputs/mineru_assets", "label": "图片资产输出目录", "sensitive": False},
    },
    "dify": {
        "api_key": {"type": "str", "default": "", "label": "Dataset API Key", "sensitive": True},
        "base_url": {"type": "str", "default": "https://api.dify.ai/v1", "label": "Base URL", "sensitive": False},
        "dataset_name": {"type": "str", "default": "Zotero Literature", "label": "知识库名称", "sensitive": False},
        "pipeline_file": {"type": "str", "default": "", "label": "Pipeline 文件路径", "sensitive": False},
        "process_mode": {"type": "select", "default": "custom", "options": ["custom", "automatic"], "label": "处理模式", "sensitive": False},
        "segment_separator": {"type": "str", "default": "\\n\\n", "label": "分段分隔符", "sensitive": False},
        "segment_max_tokens": {"type": "int", "default": 800, "min": 100, "max": 10000, "label": "段最大 Token", "sensitive": False},
        "chunk_overlap": {"type": "int", "default": 0, "min": 0, "max": 1000, "label": "分段重叠", "sensitive": False},
        "parent_mode": {"type": "str", "default": "paragraph", "label": "父级模式", "sensitive": False},
        "subchunk_separator": {"type": "str", "default": "\\n", "label": "子分段分隔符", "sensitive": False},
        "subchunk_max_tokens": {"type": "int", "default": 256, "min": 50, "max": 5000, "label": "子段最大 Token", "sensitive": False},
        "subchunk_overlap": {"type": "int", "default": 0, "min": 0, "max": 500, "label": "子段重叠", "sensitive": False},
        "remove_extra_spaces": {"type": "bool", "default": True, "label": "去除多余空格", "sensitive": False},
        "remove_urls_emails": {"type": "bool", "default": False, "label": "去除 URL/邮箱", "sensitive": False},
        "index_max_wait_s": {"type": "int", "default": 1800, "min": 60, "max": 7200, "label": "索引等待上限（秒）", "sensitive": False},
        "doc_form": {"type": "str", "default": "", "label": "文档形式", "sensitive": False},
        "doc_language": {"type": "str", "default": "", "label": "文档语言", "sensitive": False},
        "upload_delay": {"type": "int", "default": 1, "min": 0, "max": 30, "label": "上传间隔（秒）", "sensitive": False},
    },
    "md_clean": {
        "enabled": {"type": "bool", "default": True, "label": "启用清洗", "sensitive": False},
        "collapse_blank_lines": {"type": "bool", "default": True, "label": "压缩空行", "sensitive": False},
        "strip_html": {"type": "bool", "default": True, "label": "移除 HTML", "sensitive": False},
        "remove_control_chars": {"type": "bool", "default": True, "label": "移除控制字符", "sensitive": False},
        "remove_image_placeholders": {"type": "bool", "default": True, "label": "移除图片占位", "sensitive": False},
        "remove_page_numbers": {"type": "bool", "default": False, "label": "移除页码", "sensitive": False},
        "remove_watermark": {"type": "bool", "default": False, "label": "移除水印", "sensitive": False},
        "watermark_patterns": {"type": "str", "default": "", "label": "水印正则（逗号分隔）", "sensitive": False},
    },
    "image_summary": {
        "enabled": {"type": "bool", "default": True, "label": "启用图摘要回写", "sensitive": False},
        "api_base_url": {"type": "str", "default": "https://api.openai.com/v1", "label": "视觉模型 API Base URL", "sensitive": False},
        "api_key": {"type": "str", "default": "", "label": "视觉模型 API Key", "sensitive": True},
        "model": {"type": "str", "default": "gpt-4.1-mini", "label": "视觉模型名称", "sensitive": False},
        "request_timeout_s": {"type": "int", "default": 120, "min": 10, "max": 600, "label": "请求超时（秒）", "sensitive": False},
        "max_context_chars": {"type": "int", "default": 3000, "min": 500, "max": 20000, "label": "单图上下文最大字符", "sensitive": False},
        "max_images_per_doc": {"type": "int", "default": 50, "min": 0, "max": 500, "label": "单文档最多处理图片数", "sensitive": False},
        "max_tokens": {"type": "int", "default": 900, "min": 128, "max": 4000, "label": "视觉模型输出 Token 上限", "sensitive": False},
        "temperature": {"type": "float", "default": 0.1, "min": 0, "max": 2, "label": "视觉模型温度", "sensitive": False},
    },
    "smart_split": {
        "enabled": {"type": "bool", "default": True, "label": "启用智能分割", "sensitive": False},
        "strategy": {"type": "select", "default": "paragraph_wrap", "options": ["paragraph_wrap", "semantic"], "label": "分割策略", "sensitive": False},
        "split_marker": {"type": "str", "default": "<!--split-->", "label": "分割标记", "sensitive": False},
        "max_length": {"type": "int", "default": 1200, "min": 200, "max": 10000, "label": "最大段落长度", "sensitive": False},
        "min_length": {"type": "int", "default": 300, "min": 50, "max": 5000, "label": "最小段落长度", "sensitive": False},
        "min_split_score": {"type": "float", "default": 7.0, "min": 0, "max": 50, "label": "最小分割得分", "sensitive": False},
        "heading_score_bonus": {"type": "float", "default": 10.0, "min": 0, "max": 50, "label": "标题加分", "sensitive": False},
        "sentence_end_score_bonus": {"type": "float", "default": 6.0, "min": 0, "max": 50, "label": "句尾加分", "sensitive": False},
        "sentence_integrity_weight": {"type": "float", "default": 8.0, "min": 0, "max": 50, "label": "句子完整性权重", "sensitive": False},
        "length_score_factor": {"type": "int", "default": 100, "min": 1, "max": 1000, "label": "长度评分因子", "sensitive": False},
        "search_window": {"type": "int", "default": 5, "min": 1, "max": 20, "label": "搜索窗口", "sensitive": False},
        "heading_after_penalty": {"type": "float", "default": 12.0, "min": 0, "max": 50, "label": "标题后惩罚", "sensitive": False},
        "force_split_before_heading": {"type": "bool", "default": True, "label": "标题前强制分割", "sensitive": False},
        "heading_cooldown_elements": {"type": "int", "default": 2, "min": 0, "max": 10, "label": "标题冷却元素数", "sensitive": False},
        "custom_heading_regex": {"type": "str", "default": "", "label": "自定义标题正则（逗号分隔）", "sensitive": False},
    },
}

CATEGORY_LABELS = {
    "zotero": "Zotero",
    "mineru": "MinerU",
    "dify": "Dify",
    "md_clean": "Markdown 清洗",
    "image_summary": "图摘要回写",
    "smart_split": "智能分割",
}

ENV_KEY_MAP = {
    "ZOTERO_MCP_URL": ("zotero", "mcp_url"),
    "ZOTERO_COLLECTION_KEYS": ("zotero", "collection_keys"),
    "ZOTERO_COLLECTION_RECURSIVE": ("zotero", "collection_recursive"),
    "ZOTERO_COLLECTION_PAGE_SIZE": ("zotero", "collection_page_size"),
    "MINERU_API_TOKEN": ("mineru", "api_token"),
    "POLL_TIMEOUT_MINERU": ("mineru", "poll_timeout_s"),
    "MINERU_ASSET_OUTPUT_DIR": ("mineru", "asset_output_dir"),
    "DIFY_API_KEY": ("dify", "api_key"),
    "DIFY_BASE_URL": ("dify", "base_url"),
    "DIFY_DATASET_NAME": ("dify", "dataset_name"),
    "DIFY_PIPELINE_FILE": ("dify", "pipeline_file"),
    "DIFY_PROCESS_MODE": ("dify", "process_mode"),
    "DIFY_SEGMENT_SEPARATOR": ("dify", "segment_separator"),
    "DIFY_SEGMENT_MAX_TOKENS": ("dify", "segment_max_tokens"),
    "DIFY_CHUNK_OVERLAP": ("dify", "chunk_overlap"),
    "DIFY_PARENT_MODE": ("dify", "parent_mode"),
    "DIFY_SUBCHUNK_SEPARATOR": ("dify", "subchunk_separator"),
    "DIFY_SUBCHUNK_MAX_TOKENS": ("dify", "subchunk_max_tokens"),
    "DIFY_SUBCHUNK_OVERLAP": ("dify", "subchunk_overlap"),
    "DIFY_REMOVE_EXTRA_SPACES": ("dify", "remove_extra_spaces"),
    "DIFY_REMOVE_URLS_EMAILS": ("dify", "remove_urls_emails"),
    "DIFY_INDEX_MAX_WAIT": ("dify", "index_max_wait_s"),
    "DIFY_DOC_FORM": ("dify", "doc_form"),
    "DIFY_DOC_LANGUAGE": ("dify", "doc_language"),
    "DIFY_UPLOAD_DELAY": ("dify", "upload_delay"),
    "MD_CLEAN_ENABLED": ("md_clean", "enabled"),
    "MD_CLEAN_COLLAPSE_BLANK_LINES": ("md_clean", "collapse_blank_lines"),
    "MD_CLEAN_STRIP_HTML": ("md_clean", "strip_html"),
    "MD_CLEAN_REMOVE_CONTROL_CHARS": ("md_clean", "remove_control_chars"),
    "MD_CLEAN_REMOVE_IMAGE_PLACEHOLDERS": ("md_clean", "remove_image_placeholders"),
    "MD_CLEAN_REMOVE_PAGE_NUMBERS": ("md_clean", "remove_page_numbers"),
    "MD_CLEAN_REMOVE_WATERMARK": ("md_clean", "remove_watermark"),
    "MD_CLEAN_WATERMARK_PATTERNS": ("md_clean", "watermark_patterns"),
    "IMAGE_SUMMARY_ENABLED": ("image_summary", "enabled"),
    "IMAGE_SUMMARY_API_BASE_URL": ("image_summary", "api_base_url"),
    "IMAGE_SUMMARY_API_KEY": ("image_summary", "api_key"),
    "IMAGE_SUMMARY_MODEL": ("image_summary", "model"),
    "IMAGE_SUMMARY_TIMEOUT_S": ("image_summary", "request_timeout_s"),
    "IMAGE_SUMMARY_MAX_CONTEXT_CHARS": ("image_summary", "max_context_chars"),
    "IMAGE_SUMMARY_MAX_IMAGES_PER_DOC": ("image_summary", "max_images_per_doc"),
    "IMAGE_SUMMARY_MAX_TOKENS": ("image_summary", "max_tokens"),
    "IMAGE_SUMMARY_TEMPERATURE": ("image_summary", "temperature"),
    "SMART_SPLIT_STRATEGY": ("smart_split", "strategy"),
}


def build_defaults():
    """根据 schema 构建完整默认配置。"""
    defaults = {}
    for category, fields in CONFIG_SCHEMA.items():
        defaults[category] = {}
        for key, spec in fields.items():
            defaults[category][key] = spec["default"]
    return defaults


def _coerce_value(value, spec):
    """将输入值转换为 schema 定义的类型。"""
    field_type = spec["type"]
    if value is None or value == "":
        return spec["default"]

    if field_type == "bool":
        if isinstance(value, bool):
            return value
        return str(value).strip().lower() in ("true", "1", "yes", "on")

    if field_type == "int":
        try:
            v = int(value)
            if "min" in spec:
                v = max(spec["min"], v)
            if "max" in spec:
                v = min(spec["max"], v)
            return v
        except (ValueError, TypeError):
            return spec["default"]

    if field_type == "float":
        try:
            v = float(value)
            if "min" in spec:
                v = max(spec["min"], v)
            if "max" in spec:
                v = min(spec["max"], v)
            return v
        except (ValueError, TypeError):
            return spec["default"]

    if field_type == "select":
        s = str(value).strip()
        if s in spec.get("options", []):
            return s
        return spec["default"]

    return str(value)


def validate_and_coerce(data):
    """校验并修正配置数据，返回合法化后的配置。"""
    result = build_defaults()
    if not isinstance(data, dict):
        return result

    for category, fields in CONFIG_SCHEMA.items():
        cat_data = data.get(category, {})
        if not isinstance(cat_data, dict):
            continue
        for key, spec in fields.items():
            if key in cat_data:
                result[category][key] = _coerce_value(cat_data[key], spec)

    return result


def mask_sensitive(data):
    """脱敏敏感字段，仅保留末 4 位。"""
    masked = {}
    for category, fields in CONFIG_SCHEMA.items():
        masked[category] = {}
        cat_data = data.get(category, {})
        for key, spec in fields.items():
            value = cat_data.get(key, spec["default"])
            if spec.get("sensitive") and isinstance(value, str) and len(value) > 4:
                masked[category][key] = "*" * (len(value) - 4) + value[-4:]
            else:
                masked[category][key] = value
    return masked
