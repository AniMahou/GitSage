# backend/core/retriever.py
"""
Two-stage retrieval for GitSage.
Stage 1: Fast embedding search (finds 20 candidates from thousands)
Stage 2: Precise cross-encoder rerank (scores each candidate, keeps top 5)

Why two stages?
    Cross-encoder on ALL chunks = O(n) slow calls = 30+ seconds
    Embedding search first = O(log n) fast = 5ms
    Cross-encoder on top 20 = O(20) precise = 300ms
    Total = fast AND accurate
"""

from typing import List, Dict, Optional
import numpy as np
from sentence_transformers import CrossEncoder

from backend.config import RETRIEVAL_K_CANDIDATES, RETRIEVAL_K_FINAL
from backend.db.vector_store import VectorStore
from backend.core.embedder import Embedder
from backend.utils.logger import setup_logger

logger = setup_logger(__name__)


class Retriever:
    """
    Two-stage retrieval with cross-encoder re-ranking.
    
    Stage 1 (Embedding Search):
        • Embeds the user query
        • Searches ChromaDB for similar chunks
        • Returns top 20 candidates
    
    Stage 2 (Cross-Encoder Rerank):
        • For each candidate, scores (query + chunk) together
        • Cross-encoder reads both simultaneously
        • Returns top 5 most relevant
    
    Usage:
        retriever = Retriever(vector_store, embedder)
        results = retriever.retrieve(session_id, "How does auth work?")
        # Returns: List[dict] with text, metadata, relevance_score
    """
    
    def __init__(self, vector_store: VectorStore, embedder: Embedder):
        self.vector_store = vector_store
        self.embedder = embedder
        
        # Load cross-encoder model (runs locally, no API cost)
        logger.info("Loading cross-encoder model...")
        self.reranker = CrossEncoder(
            'cross-encoder/ms-marco-MiniLM-L-6-v2',
            max_length=512  # Max tokens per (query + document) pair
        )
        logger.info("Cross-encoder loaded")
    
    # ─── MAIN METHOD ───────────────────────────────────
    
    def retrieve(
        self,
        session_id: str,
        query: str,
        k_candidates: int = None,
        k_final: int = None,
        filter_dict: Optional[Dict] = None
    ) -> List[Dict]:
        """
        Full two-stage retrieval pipeline.
        
        Args:
            session_id: Which repo to search
            query: User's question
            k_candidates: How many to retrieve in Stage 1 (default: 20)
            k_final: How many to return after reranking (default: 5)
            filter_dict: Optional metadata filter
        
        Returns:
            [
                {
                    "text": "class AuthMiddleware:...",
                    "metadata": {"file": "auth.py", "start_line": 15, ...},
                    "similarity": 0.87,       # Stage 1 score
                    "rerank_score": 0.94       # Stage 2 score
                },
                ...
            ]
        """
        k_candidates = k_candidates or RETRIEVAL_K_CANDIDATES
        k_final = k_final or RETRIEVAL_K_FINAL
        
        logger.info(f"Retrieving for query: '{query[:80]}...'")
        
        # ─── STAGE 1: Embedding Search ─────────────────
        candidates = self._stage1_search(session_id, query, k_candidates, filter_dict)
        
        if not candidates:
            logger.warning("No candidates found in Stage 1")
            return []
        
        logger.info(f"Stage 1: Retrieved {len(candidates)} candidates")
        
        # If we got fewer than k_final, no need to rerank
        if len(candidates) <= k_final:
            logger.info(f"Fewer than {k_final} candidates, skipping rerank")
            return candidates
        
        # ─── STAGE 2: Cross-Encoder Rerank ─────────────
        results = self._stage2_rerank(query, candidates, k_final)
        
        logger.info(f"Stage 2: Reranked to top {len(results)}")
        
        return results
    
    # ─── STAGE 1: EMBEDDING SEARCH ────────────────────
    
    def _stage1_search(
        self,
        session_id: str,
        query: str,
        k: int,
        filter_dict: Optional[Dict] = None
    ) -> List[Dict]:
        """
        Stage 1: Fast approximate search using embeddings.
        
        1. Embed the query
        2. Search ChromaDB for similar vectors
        3. Return top-k candidates with metadata
        """
        # Embed query
        query_vector = self.embedder.embed_query(query)
        
        # Search ChromaDB
        results = self.vector_store.search(
            session_id=session_id,
            query_vector=query_vector,
            k=k,
            filter_dict=filter_dict
        )
        
        # Format results
        candidates = []
        documents = results.get('documents', [[]])[0]
        metadatas = results.get('metadatas', [[]])[0]
        distances = results.get('distances', [[]])[0]
        
        for doc, meta, dist in zip(documents, metadatas, distances):
            candidates.append({
                "text": doc,
                "metadata": meta,
                "similarity": round(1 - dist, 4),  # Convert distance to similarity
                "distance": round(dist, 4)
            })
        
        return candidates
    
    # ─── STAGE 2: CROSS-ENCODER RERANK ───────────────
    
    def _stage2_rerank(
        self,
        query: str,
        candidates: List[Dict],
        k_final: int
    ) -> List[Dict]:
        """
        Stage 2: Precise re-ranking using cross-encoder.
        
        For each candidate, the cross-encoder reads the query AND
        the chunk TOGETHER. This allows it to understand:
        • Exact word matches ("auth" in query vs "authentication" in chunk)
        • Semantic relevance (is this REALLY about what they're asking?)
        • Code structure (is this a definition or just a usage?)
        
        Much more accurate than embedding similarity, but slower.
        """
        # Create (query, document) pairs for the cross-encoder
        pairs = [[query, candidate["text"]] for candidate in candidates]
        
        # Get relevance scores
        scores = self.reranker.predict(pairs)
        
        # Convert to float (from numpy)
        scores = [float(score) for score in scores]
        
        # Sort by score descending
        ranked = sorted(
            enumerate(scores),
            key=lambda x: x[1],
            reverse=True
        )
        
        # Build final results
        results = []
        for idx, score in ranked[:k_final]:
            candidate = candidates[idx].copy()
            candidate["rerank_score"] = round(score, 4)
            results.append(candidate)
        
        # Log the reranking changes
        if len(results) >= 2:
            logger.debug(
                f"Rerank: Top score {results[0]['rerank_score']:.3f} "
                f"(was similarity {results[0]['similarity']:.3f})"
            )
        
        return results
    
    # ─── METADATA-FILTERED RETRIEVAL ──────────────────
    
    def retrieve_by_language(
        self,
        session_id: str,
        query: str,
        language: str
    ) -> List[Dict]:
        """Retrieve chunks from a specific language only."""
        return self.retrieve(
            session_id, query,
            filter_dict={"language": language}
        )
    
    def retrieve_by_file(
        self,
        session_id: str,
        query: str,
        file_pattern: str
    ) -> List[Dict]:
        """
        Retrieve chunks from files matching a pattern.
        Useful for: "How does this work in the auth module?"
        """
        return self.retrieve(
            session_id, query,
            filter_dict={"file": {"$contains": file_pattern}}
        )
    
    def retrieve_definitions(
        self,
        session_id: str,
        query: str
    ) -> List[Dict]:
        """Retrieve only class/function definitions (not usages)."""
        return self.retrieve(
            session_id, query,
            filter_dict={"chunk_type": {"$in": ["class", "function"]}}
        )