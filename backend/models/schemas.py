# backend/models/schemas.py
"""
Pydantic models for GitSage API.
These define the exact shape of every request and response.
"""

from pydantic import BaseModel, Field
from typing import Optional, List
from enum import Enum


# SESSION

class SessionCreateRequest(BaseModel):
    """User wants to create a new session (index a repo)."""
    repo_url: str = Field(
        ...,
        description="GitHub URL to clone",
        examples=["https://github.com/psf/requests"]
    )
    repo_name: Optional[str] = Field(
        None,
        description="Optional display name for the repo"
    )


class SessionStatus(str, Enum):
    """Possible states of a session."""
    CREATED = "created"        # Session exists, not yet indexing
    CLONING = "cloning"        # git clone in progress
    PARSING = "parsing"        # AST parsing files
    EMBEDDING = "embedding"    # Creating embeddings
    INDEXING = "indexing"      # Storing in ChromaDB
    READY = "ready"            # Ready for queries
    ERROR = "error"            # Something went wrong


class SessionResponse(BaseModel):
    """Information about a session."""
    session_id: str
    repo_url: str
    repo_name: Optional[str] = None
    status: SessionStatus
    progress: Optional[str] = None          # Human-readable: "Cloning repository..."
    files_found: int = 0
    chunks_indexed: int = 0
    error_message: Optional[str] = None
    created_at: Optional[str] = None


class IndexingProgress(BaseModel):
    """Progress update sent during indexing."""
    session_id: str
    status: SessionStatus
    progress: str                            # "Parsing files (45/127)..."
    files_processed: int = 0
    total_files: int = 0
    chunks_created: int = 0
    chunks_embedded: int = 0


# QUERY

class QueryRequest(BaseModel):
    """User asks a question about the codebase."""
    session_id: str = Field(
        ...,
        description="Session ID from indexing step"
    )
    query: str = Field(
        ...,
        min_length=1,
        max_length=500,
        description="Question about the codebase",
        examples=["How does the authentication middleware work?"]
    )


class SourceCitation(BaseModel):
    """A single source reference."""
    file: str                                # "middleware/auth.py"
    start_line: int                          # 15
    end_line: int                            # 47
    function_name: Optional[str] = None      # "AuthMiddleware.process"
    relevance_score: Optional[float] = None  # 0.94


class QueryResponse(BaseModel):
    """Complete response to a user query."""
    session_id: str
    query: str
    answer: str                              # The LLM's explanation
    sources: List[SourceCitation] = []       # Cited code locations
    chunks_used: int = 0                     # How many chunks informed the answer
    processing_time_ms: float = 0.0          # How long it took


class StreamToken(BaseModel):
    """A single token in a streaming response."""
    token: str
    event: str = "token"                     # "token" | "sources" | "done"


# ============================================
# CODE CHUNK (Internal)
# ============================================

class ChunkMetadata(BaseModel):
    """Metadata attached to each code chunk."""
    file: str                                # "middleware/auth.py"
    start_line: int
    end_line: int
    chunk_type: str = "function"             # "function" | "class" | "method" | "module"
    name: str                                # "AuthMiddleware" or "process_request"
    language: str = "python"                 # "python" | "javascript" | ...
    docstring: Optional[str] = None          # First docstring/comment


class CodeChunk(BaseModel):
    """A single chunk of code with its metadata."""
    chunk_id: str                            # Unique ID
    text: str                                # The actual code
    metadata: ChunkMetadata
    embedding: Optional[List[float]] = None  # Vector (added after embedding)


# ============================================
# HEALTH
# ============================================

class HealthResponse(BaseModel):
    """Health check response."""
    status: str = "healthy"
    version: str = "1.0.0"
    sessions_active: int = 0


# ============================================
# ERROR
# ============================================

class ErrorResponse(BaseModel):
    """Standard error response."""
    error: str
    detail: Optional[str] = None
    session_id: Optional[str] = None