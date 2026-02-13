import os

from dotenv import load_dotenv

load_dotenv()

ZOTERO_MCP_URL = os.getenv("ZOTERO_MCP_URL", "http://127.0.0.1:23120/mcp")

# Zotero Collection 选择
ZOTERO_COLLECTION_KEYS = os.getenv("ZOTERO_COLLECTION_KEYS", "")  # 逗号分隔，空=未指定
ZOTERO_COLLECTION_RECURSIVE = os.getenv("ZOTERO_COLLECTION_RECURSIVE", "true").lower() == "true"
ZOTERO_COLLECTION_PAGE_SIZE = max(1, int(os.getenv("ZOTERO_COLLECTION_PAGE_SIZE", "50") or "50"))

MINERU_API_TOKEN = os.getenv("MINERU_API_TOKEN", "")
MINERU_BASE_URL = "https://mineru.net/api/v4"
MINERU_BATCH_SIZE = 200
MINERU_MAX_FILE_SIZE_BYTES = 200 * 1024 * 1024
MINERU_MODEL_VERSION = "vlm"

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
