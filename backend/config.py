# backend/config.py
"""
Central configuration for GitSage.
All settings are loaded from environment variables with sensible defaults.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env file from project root
load_dotenv(Path(__file__).parent.parent / ".env")


# ============================================
# LLM (Groq - Free)
# ============================================
GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "")
LLM_MODEL: str = os.getenv("LLM_MODEL", "llama-3.3-70b-versatile")

# ============================================
# Embeddings (Local - Free)
# ============================================
EMBEDDING_MODEL: str = os.getenv("EMBEDDING_MODEL", "all-MiniLM-L6-v2")


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
RETRIEVAL_K_CANDIDATES: int = 20
RETRIEVAL_K_FINAL: int = 5
RETRIEVAL_THRESHOLD: float = 0.3


# ============================================
# Chunking Settings
# ============================================
CHUNK_MAX_CHARS: int = 1500
CHUNK_OVERLAP_CHARS: int = 100


# ============================================
# Embedding Settings
# ============================================
EMBEDDING_BATCH_SIZE: int = 100


# ============================================
# Memory Settings
# ============================================
MAX_CONVERSATION_TURNS: int = 10


# ============================================
# Logging
# ============================================
LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")


# ============================================
# Validation
# ============================================
def validate_config():
    """Ensure critical settings are present."""
    errors = []
    
    if not GROQ_API_KEY or GROQ_API_KEY == "gsk_your_groq_key_here":
        errors.append("GROQ_API_KEY is not set in .env file")
    
    if errors:
        raise ValueError(
            "Configuration errors found:\n" + 
            "\n".join(f"  • {e}" for e in errors) +
            "\n\nPlease update your .env file."
        )