# backend/db/session_store.py
"""
Session management for GitSage.
Tracks session metadata, indexing progress, and expiration.

Why a separate store from ChromaDB?
    ChromaDB stores code chunks and vectors.
    Session store tracks session state (status, progress, timestamps).
    Different data, different access patterns — separate concerns.
"""

import json
import time
from pathlib import Path
from typing import Dict, Optional, List
from datetime import datetime, timedelta
from backend.config import SESSION_EXPIRE_HOURS, PROJECT_ROOT
from backend.models.schemas import SessionStatus
from backend.utils.logger import setup_logger

logger = setup_logger(__name__)


class SessionStore:
    """
    In-memory + JSON-backed session registry.
    
    For production, replace with SQLite or Redis.
    For GitSage (portfolio project), JSON file is simple and sufficient.
    
    Usage:
        store = SessionStore()
        store.create("abc123", "https://github.com/user/repo")
        store.update_status("abc123", SessionStatus.CLONING, "Cloning repo...")
        store.get("abc123")  # → {session_id, status, ...}
    """
    
    def __init__(self):
        # Store sessions in memory + persist to JSON
        self._sessions: Dict[str, Dict] = {}
        self._storage_path = PROJECT_ROOT / "data" / "sessions.json"
        self._storage_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Load existing sessions from disk
        self._load_from_disk()
        
        logger.info(f"SessionStore initialized ({len(self._sessions)} existing sessions)")
    
    # ─── CRUD ──────────────────────────────────────────
    
    def create(
        self,
        session_id: str,
        repo_url: str,
        repo_name: Optional[str] = None
    ) -> Dict:
        """
        Create a new session.
        
        Args:
            session_id: Unique session identifier
            repo_url: GitHub URL
            repo_name: Optional display name
        
        Returns:
            Session dict
        """
        session = {
            "session_id": session_id,
            "repo_url": repo_url,
            "repo_name": repo_name or repo_url.split("/")[-1].replace(".git", ""),
            "status": SessionStatus.CREATED.value,
            "progress": None,
            "files_found": 0,
            "chunks_indexed": 0,
            "error_message": None,
            "created_at": datetime.now().isoformat(),
            "last_accessed": datetime.now().isoformat(),
        }
        
        self._sessions[session_id] = session
        self._save_to_disk()
        
        logger.info(f"Session created: {session_id} ({repo_url})")
        return session
    
    def get(self, session_id: str) -> Optional[Dict]:
        """Get a session by ID."""
        session = self._sessions.get(session_id)
        
        if session:
            # Update last accessed
            session["last_accessed"] = datetime.now().isoformat()
        
        return session
    
    def update_status(
        self,
        session_id: str,
        status: SessionStatus,
        progress: Optional[str] = None,
        **kwargs
    ):
        """
        Update session status and progress.
        
        Args:
            session_id: Session to update
            status: New status
            progress: Human-readable progress description
            **kwargs: Additional fields to update (files_found, chunks_indexed, etc.)
        """
        session = self._sessions.get(session_id)
        
        if not session:
            logger.warning(f"Session not found: {session_id}")
            return
        
        session["status"] = status.value if isinstance(status, SessionStatus) else status
        session["progress"] = progress
        session["last_accessed"] = datetime.now().isoformat()
        
        # Update additional fields
        for key, value in kwargs.items():
            if key in session:
                session[key] = value
        
        self._save_to_disk()
        
        logger.info(f"Session {session_id}: {status.value}" + 
                   (f" — {progress}" if progress else ""))
    
    def update_error(self, session_id: str, error_message: str):
        """Mark a session as errored."""
        self.update_status(
            session_id,
            SessionStatus.ERROR,
            progress="Error occurred",
            error_message=error_message
        )
        logger.error(f"Session {session_id} ERROR: {error_message}")
    
    def delete(self, session_id: str):
        """Delete a session."""
        if session_id in self._sessions:
            del self._sessions[session_id]
            self._save_to_disk()
            logger.info(f"Session deleted: {session_id}")
    
    def list_all(self) -> List[Dict]:
        """List all sessions."""
        return list(self._sessions.values())
    
    def list_active(self) -> List[Dict]:
        """List active (non-expired) sessions."""
        cutoff = datetime.now() - timedelta(hours=SESSION_EXPIRE_HOURS)
        
        active = []
        for session in self._sessions.values():
            last_accessed = datetime.fromisoformat(session["last_accessed"])
            if last_accessed > cutoff:
                active.append(session)
        
        return active
    
    # ─── CLEANUP ───────────────────────────────────────
    
    def cleanup_expired(self) -> int:
        """
        Remove sessions that haven't been accessed in SESSION_EXPIRE_HOURS.
        
        Returns:
            Number of sessions cleaned up
        """
        cutoff = datetime.now() - timedelta(hours=SESSION_EXPIRE_HOURS)
        expired_ids = []
        
        for session_id, session in self._sessions.items():
            last_accessed = datetime.fromisoformat(session["last_accessed"])
            if last_accessed < cutoff:
                expired_ids.append(session_id)
        
        for session_id in expired_ids:
            del self._sessions[session_id]
        
        if expired_ids:
            self._save_to_disk()
            logger.info(f"Cleaned up {len(expired_ids)} expired sessions")
        
        return len(expired_ids)
    
    # ─── PERSISTENCE ───────────────────────────────────
    
    def _save_to_disk(self):
        """Save sessions to JSON file."""
        try:
            with open(self._storage_path, 'w') as f:
                json.dump(self._sessions, f, indent=2, default=str)
        except Exception as e:
            logger.error(f"Failed to save sessions: {e}")
    
    def _load_from_disk(self):
        """Load sessions from JSON file."""
        if not self._storage_path.exists():
            return
        
        try:
            with open(self._storage_path, 'r') as f:
                self._sessions = json.load(f)
            logger.debug(f"Loaded {len(self._sessions)} sessions from disk")
        except Exception as e:
            logger.warning(f"Could not load sessions from disk: {e}")
            self._sessions = {}
    
    # ─── STATS ─────────────────────────────────────────
    
    def get_stats(self) -> Dict:
        """Get overall session statistics."""
        total = len(self._sessions)
        active = len(self.list_active())
        ready = sum(
            1 for s in self._sessions.values()
            if s["status"] == SessionStatus.READY.value
        )
        errored = sum(
            1 for s in self._sessions.values()
            if s["status"] == SessionStatus.ERROR.value
        )
        
        return {
            "total_sessions": total,
            "active_sessions": active,
            "ready_sessions": ready,
            "errored_sessions": errored,
            "expired_sessions": total - active,
        }