# backend/utils/logger.py
"""
Structured logging for GitSage.
Provides consistent log formatting across all modules.
"""

import logging
import sys
from pathlib import Path
from backend.config import LOG_LEVEL

# Create logs directory
LOG_DIR = Path(__file__).parent.parent.parent / "logs"
LOG_DIR.mkdir(exist_ok=True)

# Log file path
LOG_FILE = LOG_DIR / "gitsage.log"


def setup_logger(name: str) -> logging.Logger:
    """
    Create a logger with consistent formatting.
    
    Each module gets its own logger:
        logger = setup_logger(__name__)
    
    Output:
        [2024-01-15 14:30:22] [INFO] [chunker] Parsing auth.py...
    
    Logs go to BOTH:
        • Console (for development)
        • File (for debugging later)
    """
    
    logger = logging.getLogger(name)
    
    # Avoid adding handlers twice
    if logger.handlers:
        return logger
    
    logger.setLevel(getattr(logging, LOG_LEVEL.upper(), logging.INFO))
    
    # Format
    formatter = logging.Formatter(
        fmt="[%(asctime)s] [%(levelname)-5s] [%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    
    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    
    # File handler
    file_handler = logging.FileHandler(LOG_FILE)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    
    return logger


# Pre-built logger for quick imports
logger = setup_logger("gitsage")