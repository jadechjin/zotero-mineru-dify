import os

from dotenv import load_dotenv

load_dotenv()

ZOTERO_MCP_URL = os.getenv("ZOTERO_MCP_URL", "http://127.0.0.1:23120/mcp")

# Zotero collection selection
ZOTERO_COLLECTION_KEYS = os.getenv("ZOTERO_COLLECTION_KEYS", "")
ZOTERO_COLLECTION_RECURSIVE = os.getenv("ZOTERO_COLLECTION_RECURSIVE", "true").lower() == "true"
ZOTERO_COLLECTION_PAGE_SIZE = max(1, int(os.getenv("ZOTERO_COLLECTION_PAGE_SIZE", "50") or "50"))

MINERU_API_TOKEN = os.getenv("MINERU_API_TOKEN", "")
MINERU_BASE_URL = "https://mineru.net/api/v4"
MINERU_BATCH_SIZE = 200
MINERU_MAX_FILE_SIZE_BYTES = 200 * 1024 * 1024
MINERU_MODEL_VERSION = "vlm"
MINERU_ASSET_OUTPUT_DIR = os.getenv("MINERU_ASSET_OUTPUT_DIR", "outputs/mineru_assets")

DIFY_API_KEY = os.getenv("DIFY_API_KEY", "")
DIFY_BASE_URL = os.getenv("DIFY_BASE_URL", "https://api.dify.ai/v1")
DIFY_DATASET_NAME = os.getenv("DIFY_DATASET_NAME", "Zotero Literature")
DIFY_PIPELINE_FILE = os.getenv("DIFY_PIPELINE_FILE", "")

SUPPORTED_FORMATS = {".pdf", ".doc", ".docx", ".ppt", ".pptx", ".png", ".jpg", ".jpeg"}

PROGRESS_FILE = os.path.join(os.path.dirname(__file__), "progress.json")

POLL_INTERVAL_MINERU = 30
POLL_TIMEOUT_MINERU = int(os.getenv("POLL_TIMEOUT_MINERU", "7200"))
POLL_INTERVAL_DIFY = 5
DIFY_UPLOAD_DELAY = 1
DIFY_INDEX_MAX_WAIT = int(os.getenv("DIFY_INDEX_MAX_WAIT", "1800"))

DIFY_PROCESS_MODE = os.getenv("DIFY_PROCESS_MODE", "custom")
DIFY_SEGMENT_SEPARATOR = os.getenv("DIFY_SEGMENT_SEPARATOR", "\n\n")
DIFY_SEGMENT_MAX_TOKENS = int(os.getenv("DIFY_SEGMENT_MAX_TOKENS", "800"))
DIFY_CHUNK_OVERLAP = int(os.getenv("DIFY_CHUNK_OVERLAP", "0"))
DIFY_PARENT_MODE = os.getenv("DIFY_PARENT_MODE", "paragraph")
DIFY_SUBCHUNK_SEPARATOR = os.getenv("DIFY_SUBCHUNK_SEPARATOR", "\n")
DIFY_SUBCHUNK_MAX_TOKENS = int(os.getenv("DIFY_SUBCHUNK_MAX_TOKENS", "256"))
DIFY_SUBCHUNK_OVERLAP = int(os.getenv("DIFY_SUBCHUNK_OVERLAP", "0"))
DIFY_REMOVE_EXTRA_SPACES = os.getenv("DIFY_REMOVE_EXTRA_SPACES", "true").lower() == "true"
DIFY_REMOVE_URLS_EMAILS = os.getenv("DIFY_REMOVE_URLS_EMAILS", "false").lower() == "true"
DIFY_DOC_FORM = os.getenv("DIFY_DOC_FORM", "")
DIFY_DOC_LANGUAGE = os.getenv("DIFY_DOC_LANGUAGE", "")

# Markdown cleaning
MD_CLEAN_ENABLED = os.getenv("MD_CLEAN_ENABLED", "true").lower() == "true"
MD_CLEAN_COLLAPSE_BLANK_LINES = os.getenv("MD_CLEAN_COLLAPSE_BLANK_LINES", "true").lower() == "true"
MD_CLEAN_STRIP_HTML = os.getenv("MD_CLEAN_STRIP_HTML", "true").lower() == "true"
MD_CLEAN_REMOVE_CONTROL_CHARS = os.getenv("MD_CLEAN_REMOVE_CONTROL_CHARS", "true").lower() == "true"
MD_CLEAN_REMOVE_IMAGE_PLACEHOLDERS = os.getenv("MD_CLEAN_REMOVE_IMAGE_PLACEHOLDERS", "true").lower() == "true"
MD_CLEAN_REMOVE_PAGE_NUMBERS = os.getenv("MD_CLEAN_REMOVE_PAGE_NUMBERS", "false").lower() == "true"
MD_CLEAN_REMOVE_WATERMARK = os.getenv("MD_CLEAN_REMOVE_WATERMARK", "false").lower() == "true"
MD_CLEAN_WATERMARK_PATTERNS = os.getenv("MD_CLEAN_WATERMARK_PATTERNS", "")

# Image summary rewrite
IMAGE_SUMMARY_ENABLED = os.getenv("IMAGE_SUMMARY_ENABLED", "true").lower() == "true"
IMAGE_SUMMARY_API_BASE_URL = os.getenv("IMAGE_SUMMARY_API_BASE_URL", "https://api.openai.com/v1")
IMAGE_SUMMARY_API_KEY = os.getenv("IMAGE_SUMMARY_API_KEY", "")
IMAGE_SUMMARY_MODEL = os.getenv("IMAGE_SUMMARY_MODEL", "gpt-4.1-mini")
IMAGE_SUMMARY_TIMEOUT_S = int(os.getenv("IMAGE_SUMMARY_TIMEOUT_S", "120"))
IMAGE_SUMMARY_MAX_CONTEXT_CHARS = int(os.getenv("IMAGE_SUMMARY_MAX_CONTEXT_CHARS", "3000"))
IMAGE_SUMMARY_MAX_IMAGES_PER_DOC = int(os.getenv("IMAGE_SUMMARY_MAX_IMAGES_PER_DOC", "50"))
IMAGE_SUMMARY_MAX_TOKENS = int(os.getenv("IMAGE_SUMMARY_MAX_TOKENS", "900"))
IMAGE_SUMMARY_TEMPERATURE = float(os.getenv("IMAGE_SUMMARY_TEMPERATURE", "0.1"))

# Smart split
SMART_SPLIT_ENABLED = os.getenv("SMART_SPLIT_ENABLED", "true").lower() == "true"
SMART_SPLIT_STRATEGY = os.getenv("SMART_SPLIT_STRATEGY", "paragraph_wrap")
SMART_SPLIT_MARKER = os.getenv("SMART_SPLIT_MARKER", "<!--split-->")
