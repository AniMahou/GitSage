# backend/core/embedder.py
"""
Embedding generation for GitSage.
Converts code chunks into vectors using OpenAI's text-embedding-3-small.

Why embeddings?
    "How does authentication work?"  →  [0.012, -0.045, 0.078, ...]
    "class AuthMiddleware:"          →  [0.015, -0.042, 0.081, ...]
    
    These vectors are close in space because they're about the same topic.
    This is how we find relevant code without exact keyword matching.
"""

import time
from typing import List, Optional
from openai import OpenAI

from backend.config import (
    OPENAI_API_KEY,
    EMBEDDING_MODEL,
    EMBEDDING_BATCH_SIZE,
)
from backend.models.schemas import CodeChunk
from backend.utils.logger import setup_logger

logger = setup_logger(__name__)


class Embedder:
    """
    Generate embeddings for code chunks using OpenAI API.
    
    Features:
        • Batch processing (100 chunks per API call)
        • Automatic retry on failure
        • Progress logging
        • Handles rate limits gracefully
    
    Usage:
        embedder = Embedder()
        vectors = embedder.embed_chunks(chunks)
        # Returns: List[List[float]] — 1536 numbers per chunk
    """
    
    def __init__(self):
        self.client = OpenAI(api_key=OPENAI_API_KEY)
        self.model = EMBEDDING_MODEL
        self.batch_size = EMBEDDING_BATCH_SIZE
        self.max_retries = 3
        
        logger.info(f"Embedder initialized: model={self.model}, batch_size={self.batch_size}")
    
    # ─── MAIN METHOD ───────────────────────────────────
    
    def embed_chunks(self, chunks: List[CodeChunk]) -> List[CodeChunk]:
        """
        Generate embeddings for all chunks.
        Modifies chunks in-place by setting chunk.embedding.
        
        Args:
            chunks: List of CodeChunk objects
        
        Returns:
            Same chunks with embeddings populated
        """
        total = len(chunks)
        
        if total == 0:
            logger.warning("No chunks to embed")
            return chunks
        
        logger.info(f"Generating embeddings for {total} chunks...")
        start_time = time.time()
        
        # Process in batches
        for i in range(0, total, self.batch_size):
            batch = chunks[i:i + self.batch_size]
            batch_num = (i // self.batch_size) + 1
            total_batches = (total + self.batch_size - 1) // self.batch_size
            
            # Extract text from chunks
            texts = [chunk.text for chunk in batch]
            
            # Embed with retry
            vectors = self._embed_batch(texts, batch_num)
            
            # Assign vectors back to chunks
            for chunk, vector in zip(batch, vectors):
                chunk.embedding = vector
            
            # Progress
            progress = min(i + self.batch_size, total)
            logger.info(
                f"  Batch {batch_num}/{total_batches}: "
                f"Embedded {progress}/{total} chunks "
                f"({progress/total*100:.1f}%)"
            )
        
        elapsed = time.time() - start_time
        logger.info(f"Embedding complete: {total} chunks in {elapsed:.1f}s")
        
        return chunks
    
    def embed_query(self, query: str) -> List[float]:
        """
        Generate embedding for a single user query.
        
        Args:
            query: User's question about the codebase
        
        Returns:
            1536-dimensional vector
        """
        logger.debug(f"Embedding query: '{query[:80]}...'")
        
        response = self.client.embeddings.create(
            model=self.model,
            input=query
        )
        
        return response.data[0].embedding
    
    # ─── BATCH PROCESSING ─────────────────────────────
    
    def _embed_batch(self, texts: List[str], batch_num: int) -> List[List[float]]:
        """
        Embed a batch of texts with retry logic.
        
        Args:
            texts: List of chunk texts (max 100)
            batch_num: Batch number for logging
        
        Returns:
            List of embedding vectors
        """
        for attempt in range(1, self.max_retries + 1):
            try:
                response = self.client.embeddings.create(
                    model=self.model,
                    input=texts
                )
                
                # Extract vectors in order
                vectors = [data.embedding for data in response.data]
                
                return vectors
                
            except Exception as e:
                logger.warning(
                    f"  Embedding attempt {attempt}/{self.max_retries} failed: {e}"
                )
                
                if attempt < self.max_retries:
                    # Exponential backoff: 1s, 2s, 4s
                    wait = 2 ** (attempt - 1)
                    logger.info(f"  Retrying in {wait}s...")
                    time.sleep(wait)
                else:
                    logger.error(f"  All {self.max_retries} attempts failed!")
                    raise RuntimeError(f"Failed to embed batch {batch_num}: {e}")
    
    # ─── UTILITIES ─────────────────────────────────────
    
    def count_tokens_estimate(self, text: str) -> int:
        """
        Rough token count estimate.
        ~4 characters per token for English text.
        """
        return len(text) // 4
    
    def estimate_cost(self, num_chunks: int, avg_chars_per_chunk: int = 1000) -> float:
        """
        Estimate the cost of embedding a repository.
        
        text-embedding-3-small: $0.02 per 1M tokens
        
        Args:
            num_chunks: Number of chunks
            avg_chars_per_chunk: Average characters per chunk
        
        Returns:
            Estimated cost in USD
        """
        estimated_tokens = (num_chunks * avg_chars_per_chunk) / 4
        cost = (estimated_tokens / 1_000_000) * 0.02
        return cost