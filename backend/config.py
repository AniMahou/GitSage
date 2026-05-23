import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env file from project root
# .env is two levels up from this file:
#   GitSage/backend/config.py → GitSage/.env
load_dotenv(Path(__file__).parent.parent / ".env")


# ============================================
# OpenAI
# ============================================
OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
LLM_MODEL: str = os.getenv("LLM_MODEL", "gpt-4o-mini")
EMBEDDING_MODEL: str = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")


# ============================================
# Paths
# ============================================
# Project root directory
PROJECT_ROOT: Path = Path(__file__).parent.parent

# Where cloned repos are stored
REPO_STORAGE_PATH: Path = Path(os.getenv("REPO_STORAGE_PATH", "./data/repos"))
if not REPO_STORAGE_PATH.is_absolute():
    REPO_STORAGE_PATH = PROJECT_ROOT / REPO_STORAGE_PATH

# Where ChromaDB persists vectors
CHROMA_PERSIST_PATH: Path = Path(os.getenv("CHROMA_PERSIST_PATH", "./data/chroma_db"))
if not CHROMA_PERSIST_PATH.is_absolute():
    CHROMA_PERSIST_PATH = PROJECT_ROOT / CHROMA_PERSIST_PATH


# ============================================
# Server
# ============================================
HOST: str = os.getenv("HOST", "127.0.0.1")
PORT: int = int(os.getenv("PORT", "8000"))


# ============================================
# Session
# ============================================
SESSION_EXPIRE_HOURS: int = int(os.getenv("SESSION_EXPIRE_HOURS", "24"))


# ============================================
# Retrieval Settings
# ============================================
# How many candidates to retrieve in Stage 1
RETRIEVAL_K_CANDIDATES: int = 20

# How many chunks to keep after re-ranking
RETRIEVAL_K_FINAL: int = 5

# Minimum similarity score to consider
RETRIEVAL_THRESHOLD: float = 0.3


# ============================================
# Chunking Settings
# ============================================
# Maximum characters per code chunk
CHUNK_MAX_CHARS: int = 1500

# Overlap between chunks (for fallback parser)
CHUNK_OVERLAP_CHARS: int = 100


# ============================================
# Embedding Settings
# ============================================
# Batch size for embedding API calls
EMBEDDING_BATCH_SIZE: int = 100


# ============================================
# Memory Settings
# ============================================
# Maximum conversation turns to remember
MAX_CONVERSATION_TURNS: int = 10


# ============================================
# Logging
# ============================================
LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")


# ============================================
# Validation (runs on import)
# ============================================
def validate_config():
    """Ensure critical settings are present."""
    errors = []
    
    if not OPENAI_API_KEY or OPENAI_API_KEY == "sk-your-actual-key-here":
        errors.append("OPENAI_API_KEY is not set in .env file")
    
    if errors:
        raise ValueError(
            "Configuration errors found:\n" + 
            "\n".join(f"  • {e}" for e in errors) +
            "\n\nPlease update your .env file."
        )

# Uncomment to enforce validation on startup:
# validate_config()