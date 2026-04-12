# RAG Configuration Constants for Spec 012

# Weights for hybrid ranking
VECTOR_WEIGHT = 0.7
LEXICAL_WEIGHT = 0.3

# Search and retrieval limits
CANDIDATE_POOL_SIZE = 20
PER_DOC_CAP = 2

# Database path
DB_PATH = "rag_v2.db"

# Grounding Defaults (Spec 018)
DEFAULT_MODEL = "granite4:3b"
DEFAULT_MODE = "chat"
AGENT_PURPOSE = "General assistant with chat, document, and personal modes"
DEFAULT_LOCATION = "unknown" # Can be overridden by env or specific config
DEFAULT_TIMEZONE = None # If None, use system timezone

# Ingestion Concurrency (Spec 021)
import os
INGESTION_MAX_WORKERS = min(4, os.cpu_count() or 1)
INGESTION_EMBED_MAX_WORKERS = min(4, os.cpu_count() or 1)

# Ingestion Extraction (Spec 022)
ENABLE_MARKITDOWN = True
PDF_MIN_TEXT_THRESHOLD_FOR_NO_OCR = 500

# Upload Support (Spec 023)
SUPPORTED_UPLOAD_EXTENSIONS = (
    ".pdf",
    ".docx",
    ".pptx",
    ".xlsx",
    ".xls",
    ".csv",
    ".txt",
    ".md",
)
SUPPORTED_UPLOAD_TYPES_DISPLAY = "PDF, DOCX, PPTX, XLSX, XLS, CSV, TXT, MD."

# Spreadsheet / Layout Extraction (Spec 024)
SPREADSHEET_HEADER_SCAN_LIMIT = 10
LAYOUT_COLUMN_GAP_THRESHOLD = 8
LAYOUT_SHORT_LINE_MAX = 80
