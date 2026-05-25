# backend/main.py
"""
GitSage API Server.
FastAPI application that orchestrates the entire pipeline:
    GitHub URL → Clone → Chunk → Embed → Store → Query → Answer

Endpoints:
    POST   /api/sessions              Create a new session
    POST   /api/sessions/{id}/index   Index a repository
    POST   /api/sessions/{id}/query   Ask a question (streaming)
    GET    /api/sessions/{id}/status  Check indexing progress
    DELETE /api/sessions/{id}         Clean up session
    GET    /api/health                Health check
"""

import uuid
import time
from typing import Optional
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from sse_starlette.sse import EventSourceResponse

from backend.config import HOST, PORT
from backend.models.schemas import (
    SessionCreateRequest,
    SessionResponse,
    SessionStatus,
    IndexingProgress,
    QueryRequest,
    QueryResponse,
    SourceCitation,
    HealthResponse,
    ErrorResponse,
)
from backend.core.repo_handler import RepoHandler
from backend.core.chunker import CodeChunker
from backend.core.embedder import Embedder
from backend.core.retriever import Retriever
from backend.core.generator import Generator
from backend.core.memory import ConversationMemory
from backend.db.vector_store import VectorStore
from backend.db.session_store import SessionStore
from backend.utils.logger import setup_logger

logger = setup_logger(__name__)


# ============================================
# Application Lifecycle
# ============================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events."""
    logger.info("🚀 GitSage API starting...")
    logger.info(f"   Host: {HOST}:{PORT}")
    logger.info(f"   LLM: {LLM_MODEL}")
    
    # Initialize global components
    app.state.repo_handler = RepoHandler()
    app.state.chunker = CodeChunker()
    app.state.embedder = Embedder()
    app.state.vector_store = VectorStore()
    app.state.session_store = SessionStore()
    app.state.retriever = Retriever(app.state.vector_store, app.state.embedder)
    app.state.generator = Generator()
    app.state.memory = ConversationMemory()
    
    logger.info("✅ All components initialized")
    
    yield
    
    logger.info("👋 GitSage API shutting down")


# ============================================
# FastAPI App
# ============================================

app = FastAPI(
    title="GitSage API",
    description="Codebase Q&A Bot — Ask questions about any GitHub repository",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS — allow frontend to connect
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, restrict to your frontend URL
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================
# Imports (lazy for clean startup)
# ============================================
from backend.config import LLM_MODEL


# ============================================
# HEALTH CHECK
# ============================================

@app.get("/api/health", response_model=HealthResponse)
async def health_check():
    """Check if the API is running."""
    sessions_active = len(app.state.session_store.list_active())
    
    return HealthResponse(
        status="healthy",
        version="1.0.0",
        sessions_active=sessions_active
    )


# ============================================
# SESSION ENDPOINTS
# ============================================

@app.post("/api/sessions", response_model=SessionResponse)
async def create_session(request: SessionCreateRequest):
    """
    Create a new session for a repository.
    
    This does NOT start indexing — call /index next.
    Separating creation from indexing gives the frontend
    immediate feedback and allows async processing.
    """
    # Validate URL
    if not app.state.repo_handler.validate_url(request.repo_url):
        raise HTTPException(status_code=400, detail="Invalid repository URL")
    
    # Create session
    session_id = uuid.uuid4().hex[:16]
    
    session = app.state.session_store.create(
        session_id=session_id,
        repo_url=request.repo_url,
        repo_name=request.repo_name
    )
    
    logger.info(f"Session created: {session_id} → {request.repo_url}")
    
    return SessionResponse(
        session_id=session_id,
        repo_url=request.repo_url,
        repo_name=session.get("repo_name"),
        status=SessionStatus.CREATED,
        progress="Session created. Ready to index.",
        created_at=session.get("created_at")
    )


@app.get("/api/sessions/{session_id}", response_model=SessionResponse)
async def get_session(session_id: str):
    """Get session information."""
    session = app.state.session_store.get(session_id)
    
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    return SessionResponse(
        session_id=session_id,
        repo_url=session["repo_url"],
        repo_name=session.get("repo_name"),
        status=SessionStatus(session["status"]),
        progress=session.get("progress"),
        files_found=session.get("files_found", 0),
        chunks_indexed=session.get("chunks_indexed", 0),
        error_message=session.get("error_message"),
        created_at=session.get("created_at")
    )


@app.delete("/api/sessions/{session_id}")
async def delete_session(session_id: str):
    """Delete a session and all its data."""
    session = app.state.session_store.get(session_id)
    
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    # Clean up vector store
    app.state.vector_store.delete_collection(session_id)
    
    # Clean up cloned repo
    app.state.repo_handler.cleanup(session_id)
    
    # Clear memory
    app.state.memory.clear_history(session_id)
    
    # Remove session
    app.state.session_store.delete(session_id)
    
    logger.info(f"Session deleted: {session_id}")
    
    return {"status": "deleted", "session_id": session_id}


# ============================================
# INDEXING ENDPOINT
# ============================================

@app.post("/api/sessions/{session_id}/index")
async def index_repository(
    session_id: str,
    background_tasks: BackgroundTasks
):
    """
    Index a repository for the given session.
    
    This launches a BACKGROUND TASK because indexing takes 30-60 seconds.
    The frontend polls GET /status for progress updates.
    
    Pipeline:
        1. Clone repository
        2. Walk file tree
        3. Parse code into chunks (AST)
        4. Generate embeddings
        5. Store in ChromaDB
    """
    session = app.state.session_store.get(session_id)
    
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    repo_url = session["repo_url"]
    
    # Launch background indexing task
    background_tasks.add_task(_index_pipeline, session_id, repo_url)
    
    logger.info(f"Indexing started for session {session_id}")
    
    return {
        "session_id": session_id,
        "status": "indexing",
        "message": "Indexing started. Poll GET /api/sessions/{session_id} for progress."
    }


async def _index_pipeline(session_id: str, repo_url: str):
    """
    Full indexing pipeline — runs in background.
    
    This is the complete flow:
        Clone → Parse → Embed → Store
    """
    start_time = time.time()
    
    try:
        # ─── STEP 1: Clone Repository ─────────────────
        app.state.session_store.update_status(
            session_id, SessionStatus.CLONING,
            "Cloning repository..."
        )
        
        repo_path = app.state.repo_handler.clone(repo_url, session_id)
        
        # ─── STEP 2: Find Source Files ────────────────
        app.state.session_store.update_status(
            session_id, SessionStatus.PARSING,
            "Finding source files..."
        )
        
        source_files = app.state.repo_handler.get_source_files(repo_path)
        stats = app.state.repo_handler.get_file_stats(source_files)
        
        app.state.session_store.update_status(
            session_id, SessionStatus.PARSING,
            f"Found {len(source_files)} source files",
            files_found=len(source_files)
        )
        
        if not source_files:
            raise ValueError("No supported source files found in repository")
        
        # ─── STEP 3: Chunk Code ────────────────────────
        app.state.session_store.update_status(
            session_id, SessionStatus.PARSING,
            f"Parsing {len(source_files)} files..."
        )
        
        chunks = app.state.chunker.chunk_directory(source_files)
        
        app.state.session_store.update_status(
            session_id, SessionStatus.PARSING,
            f"Created {len(chunks)} code chunks"
        )
        
        # ─── STEP 4: Create ChromaDB Collection ────────
        app.state.vector_store.create_collection(session_id)
        
        # ─── STEP 5: Generate Embeddings ──────────────
        app.state.session_store.update_status(
            session_id, SessionStatus.EMBEDDING,
            f"Generating embeddings for {len(chunks)} chunks..."
        )
        
        chunks = app.state.embedder.embed_chunks(chunks)
        
        # ─── STEP 6: Store in ChromaDB ────────────────
        app.state.session_store.update_status(
            session_id, SessionStatus.INDEXING,
            f"Storing {len(chunks)} chunks in vector database..."
        )
        
        app.state.vector_store.add_chunks(session_id, chunks)
        
        # ─── SUCCESS ──────────────────────────────────
        elapsed = time.time() - start_time
        
        app.state.session_store.update_status(
            session_id, SessionStatus.READY,
            f"Indexed {len(chunks)} chunks from {len(source_files)} files in {elapsed:.1f}s",
            chunks_indexed=len(chunks),
            files_found=len(source_files)
        )
        
        logger.info(
            f"✅ Indexing complete for {session_id}: "
            f"{len(chunks)} chunks in {elapsed:.1f}s"
        )
        
    except Exception as e:
        logger.error(f"❌ Indexing failed for {session_id}: {e}")
        app.state.session_store.update_error(session_id, str(e))


# ============================================
# QUERY ENDPOINT (STREAMING)
# ============================================

@app.post("/api/sessions/{session_id}/query")
async def query_repository(session_id: str, request: QueryRequest):
    """
    Ask a question about the indexed repository.
    
    Returns a STREAM of Server-Sent Events (SSE):
        event: token     → Individual answer tokens
        event: sources   → Source citations
        event: done      → Stream complete
    
    The frontend displays tokens as they arrive (like ChatGPT).
    """
    session = app.state.session_store.get(session_id)
    
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    if session["status"] != SessionStatus.READY.value:
        raise HTTPException(
            status_code=400,
            detail=f"Session not ready. Current status: {session['status']}"
        )
    
    query = request.query.strip()
    
    if not query:
        raise HTTPException(status_code=400, detail="Query cannot be empty")
    
    logger.info(f"Query for session {session_id[:8]}: '{query[:80]}...'")
    
    # ─── STEP 1: Rewrite Query with Memory ────────────
    rewritten_query = app.state.memory.rewrite_query(session_id, query)
    
    # ─── STEP 2: Retrieve Relevant Chunks ────────────
    retrieval_start = time.time()
    
    chunks = app.state.retriever.retrieve(
        session_id=session_id,
        query=rewritten_query
    )
    
    retrieval_time = (time.time() - retrieval_start) * 1000
    
    if not chunks:
        # No relevant chunks found
        async def no_results_stream():
            yield {
                "event": "token",
                "data": "I couldn't find any relevant code for that question. "
                        "The repository may not contain the logic you're asking about."
            }
            yield {"event": "done", "data": ""}
        
        return EventSourceResponse(no_results_stream())
    
    # ─── STEP 3: Get Conversation History ────────────
    history = app.state.memory.get_context_for_generator(session_id)
    
    # ─── STEP 4: Stream Answer ────────────────────────
    async def stream_answer():
        """Stream tokens as Server-Sent Events."""
        full_answer = ""
        
        try:
            # Stream tokens from generator
            for token in app.state.generator.generate_stream(
                query=query,
                chunks=chunks,
                conversation_history=history
            ):
                full_answer += token
                yield {
                    "event": "token",
                    "data": token
                }
            
            # Send sources
            sources = []
            seen = set()
            for chunk in chunks:
                meta = chunk.get("metadata", {})
                file = meta.get("file", "unknown")
                line = meta.get("start_line", "?")
                key = f"{file}:{line}"
                
                if key not in seen:
                    seen.add(key)
                    sources.append({
                        "file": file,
                        "start_line": line,
                        "end_line": meta.get("end_line", "?"),
                        "function_name": meta.get("name", ""),
                        "relevance_score": chunk.get("rerank_score") or chunk.get("similarity", 0)
                    })
            
            yield {
                "event": "sources",
                "data": sources
            }
            
            # Signal completion
            yield {
                "event": "done",
                "data": {
                    "chunks_used": len(chunks),
                    "retrieval_time_ms": retrieval_time
                }
            }
            
            # Store in memory for follow-up questions
            app.state.memory.add_exchange(session_id, query, full_answer)
            
        except Exception as e:
            logger.error(f"Streaming error: {e}")
            yield {
                "event": "error",
                "data": str(e)
            }
    
    return EventSourceResponse(stream_answer())


# ============================================
# QUERY ENDPOINT (NON-STREAMING)
# ============================================

@app.post("/api/sessions/{session_id}/query/sync", response_model=QueryResponse)
async def query_repository_sync(session_id: str, request: QueryRequest):
    """
    Ask a question and get the COMPLETE answer at once.
    Use this for testing or when streaming isn't needed.
    """
    session = app.state.session_store.get(session_id)
    
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    if session["status"] != SessionStatus.READY.value:
        raise HTTPException(
            status_code=400,
            detail=f"Session not ready. Current status: {session['status']}"
        )
    
    query = request.query.strip()
    
    # Rewrite with memory
    rewritten_query = app.state.memory.rewrite_query(session_id, query)
    
    # Retrieve
    start_time = time.time()
    chunks = app.state.retriever.retrieve(session_id, rewritten_query)
    retrieval_time = (time.time() - start_time) * 1000
    
    if not chunks:
        return QueryResponse(
            session_id=session_id,
            query=query,
            answer="I couldn't find any relevant code for that question.",
            sources=[],
            chunks_used=0,
            processing_time_ms=retrieval_time
        )
    
    # Get history
    history = app.state.memory.get_context_for_generator(session_id)
    
    # Generate
    result = app.state.generator.generate_with_sources(query, chunks, history)
    
    # Store in memory
    app.state.memory.add_exchange(session_id, query, result["answer"])
    
    # Build sources
    sources = [
        SourceCitation(
            file=s["file"],
            start_line=s["start_line"],
            end_line=s["end_line"],
            function_name=s.get("function_name"),
            relevance_score=s.get("relevance_score")
        )
        for s in result["sources"]
    ]
    
    return QueryResponse(
        session_id=session_id,
        query=query,
        answer=result["answer"],
        sources=sources,
        chunks_used=len(chunks),
        processing_time_ms=retrieval_time
    )


# ============================================
# MAIN ENTRY POINT
# ============================================

if __name__ == "__main__":
    import uvicorn
    
    logger.info(f"Starting GitSage API on {HOST}:{PORT}")
    
    uvicorn.run(
        "backend.main:app",
        host=HOST,
        port=PORT,
        reload=True,         # Auto-reload on code changes
        log_level="info"
    )