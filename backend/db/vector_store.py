# backend/db/vector_store.py
"""
Vector database operations for GitSage.
Stores code chunks with embeddings in ChromaDB for semantic search.

Why ChromaDB?
    • Python-native — no separate server needed
    • Persistent — survives restarts
    • HNSW index — fast approximate nearest neighbor search
    • Metadata filtering — search by file, language, chunk type
"""

import chromadb
from chromadb.config import Settings
from typing import List, Optional, Dict
from backend.config import CHROMA_PERSIST_PATH
from backend.models.schemas import CodeChunk
from backend.utils.logger import setup_logger

logger = setup_logger(__name__)


class VectorStore:
    """
    ChromaDB wrapper for storing and searching code embeddings.
    
    Each session gets its own collection: "repo_{session_id}"
    This isolates different repositories from each other.
    
    Usage:
        store = VectorStore()
        store.create_collection("session_abc123")
        store.add_chunks("session_abc123", chunks)
        results = store.search("session_abc123", query_vector, k=20)
    """
    
    def __init__(self):
        # Ensure persist directory exists
        CHROMA_PERSIST_PATH.mkdir(parents=True, exist_ok=True)
        
        # Initialize persistent client
        self.client = chromadb.PersistentClient(
            path=str(CHROMA_PERSIST_PATH),
            settings=Settings(
                anonymized_telemetry=False,  # Don't send usage data
                allow_reset=True             # Allow reset for testing
            )
        )
        
        logger.info(f"VectorStore initialized at {CHROMA_PERSIST_PATH}")
    
    # ─── COLLECTION MANAGEMENT ────────────────────────
    
    def create_collection(self, session_id: str) -> str:
        """
        Create a new collection for a session.
        
        Collection name format: "repo_{session_id}"
        
        Args:
            session_id: Unique session identifier
        
        Returns:
            Collection name
        
        Raises:
            ValueError: If collection already exists
        """
        collection_name = self._collection_name(session_id)
        
        # Check if exists
        existing = self.client.list_collections()
        if collection_name in [c.name for c in existing]:
            logger.warning(f"Collection {collection_name} already exists, deleting old one")
            self.client.delete_collection(collection_name)
        
        collection = self.client.create_collection(
            name=collection_name,
            metadata={
                "hnsw:space": "cosine",          # Cosine similarity
                "hnsw:M": 32,                    # Connections per node
                "hnsw:construction_ef": 200,      # Build-time accuracy
                "hnsw:search_ef": 100,            # Query-time accuracy
                "description": f"Code chunks for session {session_id}"
            }
        )
        
        logger.info(f"Created collection: {collection_name}")
        return collection_name
    
    def get_collection(self, session_id: str):
        """Get an existing collection by session ID."""
        collection_name = self._collection_name(session_id)
        return self.client.get_collection(collection_name)
    
    def delete_collection(self, session_id: str):
        """Delete a session's collection."""
        collection_name = self._collection_name(session_id)
        
        try:
            self.client.delete_collection(collection_name)
            logger.info(f"Deleted collection: {collection_name}")
        except Exception as e:
            logger.warning(f"Could not delete collection {collection_name}: {e}")
    
    def collection_exists(self, session_id: str) -> bool:
        """Check if a session has an existing collection."""
        collection_name = self._collection_name(session_id)
        existing = self.client.list_collections()
        return collection_name in [c.name for c in existing]
    
    # ─── ADDING DATA ──────────────────────────────────
    
    def add_chunks(self, session_id: str, chunks: List[CodeChunk], batch_size: int = 100):
        """
        Add code chunks to a session's collection.
        
        Args:
            session_id: Session to add to
            chunks: Code chunks with embeddings already populated
            batch_size: How many chunks to add per batch
        """
        collection = self.get_collection(session_id)
        total = len(chunks)
        
        logger.info(f"Adding {total} chunks to {self._collection_name(session_id)}...")
        
        for i in range(0, total, batch_size):
            batch = chunks[i:i + batch_size]
            
            # Prepare data
            ids = [chunk.chunk_id for chunk in batch]
            documents = [chunk.text for chunk in batch]
            embeddings = [chunk.embedding for chunk in batch]
            metadatas = [
                {
                    "file": chunk.metadata.file,
                    "start_line": chunk.metadata.start_line,
                    "end_line": chunk.metadata.end_line,
                    "chunk_type": chunk.metadata.chunk_type,
                    "name": chunk.metadata.name,
                    "language": chunk.metadata.language,
                    "docstring": chunk.metadata.docstring or "",
                }
                for chunk in batch
            ]
            
            # Add to ChromaDB
            collection.add(
                ids=ids,
                documents=documents,
                embeddings=embeddings,
                metadatas=metadatas
            )
            
            progress = min(i + batch_size, total)
            if progress % 200 == 0 or progress == total:
                logger.info(f"  Added {progress}/{total} chunks")
        
        logger.info(f"All {total} chunks added to {self._collection_name(session_id)}")
    
    # ─── SEARCHING ─────────────────────────────────────
    
    def search(
        self,
        session_id: str,
        query_vector: List[float],
        k: int = 20,
        filter_dict: Optional[Dict] = None
    ) -> Dict:
        """
        Search for similar chunks.
        
        Args:
            session_id: Session to search in
            query_vector: Embedding of the user's question (1536d)
            k: Number of results to return
            filter_dict: Optional metadata filter
                Example: {"language": "python"}
                Example: {"chunk_type": {"$in": ["class", "function"]}}
        
        Returns:
            {
                "ids": [["chunk_000123", ...]],
                "documents": [["class AuthMiddleware:\n    def __init__...", ...]],
                "metadatas": [[{"file": "auth.py", ...}, ...]],
                "distances": [[0.13, 0.21, ...]]
            }
        """
        collection = self.get_collection(session_id)
        
        logger.debug(
            f"Searching {self._collection_name(session_id)} "
            f"(k={k}, filter={filter_dict})"
        )
        
        results = collection.query(
            query_embeddings=[query_vector],
            n_results=k,
            where=filter_dict,
            include=["documents", "metadatas", "distances"]
        )
        
        return results
    
    def search_by_text(
        self,
        session_id: str,
        query_text: str,
        k: int = 20,
        filter_dict: Optional[Dict] = None
    ) -> Dict:
        """
        Search using raw text (ChromaDB handles embedding).
        Useful for quick testing without manual embedding.
        """
        collection = self.get_collection(session_id)
        
        results = collection.query(
            query_texts=[query_text],
            n_results=k,
            where=filter_dict,
            include=["documents", "metadatas", "distances"]
        )
        
        return results
    
    # ─── STATS ─────────────────────────────────────────
    
    def get_collection_stats(self, session_id: str) -> Dict:
        """Get statistics about a collection."""
        collection = self.get_collection(session_id)
        count = collection.count()
        
        return {
            "collection_name": self._collection_name(session_id),
            "total_chunks": count,
        }
    
    def list_all_collections(self) -> List[str]:
        """List all collection names."""
        return [c.name for c in self.client.list_collections()]
    
    # ─── HELPERS ───────────────────────────────────────
    
    def _collection_name(self, session_id: str) -> str:
        """Convert session ID to collection name."""
        # Sanitize: only allow alphanumeric, hyphens, underscores
        safe_id = "".join(c for c in session_id if c.isalnum() or c in '-_')
        return f"repo_{safe_id}"