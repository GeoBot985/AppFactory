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
