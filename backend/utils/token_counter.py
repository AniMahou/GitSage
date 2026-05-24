# backend/utils/token_counter.py
"""
Token counting for OpenAI models.
Ensures we never exceed context window limits.
"""

import tiktoken
from typing import List, Dict
from backend.config import LLM_MODEL


class TokenCounter:
    """
    Count tokens and enforce budget limits.
    
    Why this matters:
        GPT-4o-mini has a 128K context window.
        But we want to use ~3K for context to keep costs low.
        This class helps us stay within budget.
    """
    
    def __init__(self, model: str = None):
        self.model = model or LLM_MODEL
        try:
            self.encoding = tiktoken.encoding_for_model(self.model)
        except KeyError:
            # Fallback for unknown models
            self.encoding = tiktoken.get_encoding("cl100k_base")
    
    def count(self, text: str) -> int:
        """
        Count tokens in a text string.
        
        Example:
            counter.count("Hello world") → 2
        """
        return len(self.encoding.encode(text))
    
    def count_messages(self, messages: List[Dict[str, str]]) -> int:
        """
        Count tokens in a chat messages array.
        
        Accounts for message overhead (role tokens, formatting).
        
        Args:
            messages: [{"role": "system", "content": "..."}, ...]
        """
        total = 0
        for msg in messages:
            total += self.count(msg.get("content", ""))
            total += 4  # Overhead per message (role, formatting)
        total += 2  # Overall overhead
        return total
    
    def count_chunks(self, chunks: List[dict]) -> int:
        """
        Count total tokens across retrieved chunks.
        
        Args:
            chunks: [{"text": "...", "metadata": {...}}, ...]
        """
        total = 0
        for chunk in chunks:
            total += self.count(chunk.get("text", ""))
        return total
    
    def fits_in_budget(
        self,
        system_prompt: str,
        context: str,
        query: str,
        max_tokens: int = 3000,
        reserve_for_response: int = 1000
    ) -> bool:
        """
        Check if everything fits in the token budget.
        
        Args:
            system_prompt: The system message
            context: All retrieved chunks combined
            query: User's question
            max_tokens: Our self-imposed budget
            reserve_for_response: Space reserved for LLM output
        
        Returns:
            True if everything fits
        """
        total = (
            self.count(system_prompt) +
            self.count(context) +
            self.count(query) +
            10  # Message overhead
        )
        
        budget = max_tokens - reserve_for_response
        return total <= budget
    
    def truncate_context(
        self,
        chunks: List[dict],
        max_tokens: int = 3000,
        reserve_for_response: int = 1000
    ) -> List[dict]:
        """
        Truncate chunks to fit within token budget.
        
        Keeps highest-ranked chunks first.
        
        Args:
            chunks: Retrieved chunks, sorted by relevance
            max_tokens: Maximum tokens for context
            reserve_for_response: Space for LLM output
        
        Returns:
            Truncated list of chunks that fit in budget
        """
        budget = max_tokens - reserve_for_response
        current_tokens = 0
        kept_chunks = []
        
        for chunk in chunks:
            chunk_tokens = self.count(chunk.get("text", ""))
            
            if current_tokens + chunk_tokens > budget:
                # Try to include a partial chunk if we have room
                remaining = budget - current_tokens
                if remaining > 50:  # Minimum useful size
                    # Truncate chunk text
                    tokens = self.encoding.encode(chunk["text"])
                    truncated_tokens = tokens[:remaining]
                    truncated_text = self.encoding.decode(truncated_tokens)
                    
                    partial_chunk = chunk.copy()
                    partial_chunk["text"] = truncated_text + "..."
                    partial_chunk["truncated"] = True
                    kept_chunks.append(partial_chunk)
                break
            
            kept_chunks.append(chunk)
            current_tokens += chunk_tokens
        
        return kept_chunks
    
    def estimate_cost(
        self,
        input_tokens: int,
        output_tokens: int
    ) -> float:
        """
        Estimate USD cost for an API call.
        
        GPT-4o-mini pricing:
            Input:  $0.15 per 1M tokens
            Output: $0.60 per 1M tokens
        """
        input_cost = (input_tokens / 1_000_000) * 0.15
        output_cost = (output_tokens / 1_000_000) * 0.60
        return input_cost + output_cost


# Global instance for easy import
counter = TokenCounter()