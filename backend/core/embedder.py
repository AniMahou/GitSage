# backend/core/embedder.py
"""
Free local embedding generation for GitSage.
Uses Sentence-Transformers (all-MiniLM-L6-v2) — no API costs, no rate limits.

Dimensions: 384 (smaller than OpenAI's 1536, but good enough for code search)
"""

import time
from typing import List
from sentence_transformers import SentenceTransformer

from backend.config import EMBEDDING_BATCH_SIZE
from backend.models.schemas import CodeChunk
from backend.utils.logger import setup_logger

logger = setup_logger(__name__)


class Embedder:
    """
    Generate embeddings using free local model.
    
    Model: all-MiniLM-L6-v2
    Dimensions: 384
    Speed: ~100 chunks/second on CPU
    Cost: FREE forever
    """
    
    def __init__(self):
        logger.info("Loading local embedding model (all-MiniLM-L6-v2)...")
        self.model = SentenceTransformer('all-MiniLM-L6-v2')
        self.batch_size = EMBEDDING_BATCH_SIZE
        
        logger.info(f"Embedder ready: model=all-MiniLM-L6-v2, dims=384, batch={self.batch_size}")
    
    def embed_chunks(self, chunks: List[CodeChunk]) -> List[CodeChunk]:
        """Generate embeddings for all chunks (modifies in-place)."""
        total = len(chunks)
        
        if total == 0:
            logger.warning("No chunks to embed")
            return chunks
        
        logger.info(f"Generating embeddings for {total} chunks...")
        start_time = time.time()
        
        for i in range(0, total, self.batch_size):
            batch = chunks[i:i + self.batch_size]
            batch_num = (i // self.batch_size) + 1
            total_batches = (total + self.batch_size - 1) // self.batch_size
            
            texts = [chunk.text for chunk in batch]
            vectors = self.model.encode(texts).tolist()
            
            for chunk, vector in zip(batch, vectors):
                chunk.embedding = vector
            
            progress = min(i + self.batch_size, total)
            if batch_num % 5 == 0 or batch_num == total_batches:
                logger.info(f"  Batch {batch_num}/{total_batches}: {progress}/{total} chunks")
        
        elapsed = time.time() - start_time
        logger.info(f"Embedding complete: {total} chunks in {elapsed:.1f}s")
        
        return chunks
    
    def embed_query(self, query: str) -> List[float]:
        """Embed a single user query."""
        return self.model.encode(query).tolist()

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