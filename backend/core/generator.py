# backend/core/generator.py
"""
Answer generation for GitSage.
Builds prompts with code context and calls GPT-4o-mini.

The LLM NEVER accesses the internet, reads files, or queries the database.
EVERYTHING it needs is in the prompt we construct.
This is the "grounding" principle — the answer must come from the context.
"""

from typing import List, Dict, Optional, Generator
from openai import OpenAI

from backend.config import OPENAI_API_KEY, LLM_MODEL
from backend.utils.logger import setup_logger
from backend.utils.token_counter import counter

logger = setup_logger(__name__)


# ============================================
# System Prompt — The AI's Constitution
# ============================================

SYSTEM_PROMPT = """You are an expert code reviewer and software architect for GitSage.

YOUR JOB:
Explain code clearly, accurately, and with proper citations.

CRITICAL RULES:
1. Answer ONLY using the provided CODEBASE CONTEXT.
2. Every claim about code MUST cite the source like this: [file:line]
   Example: "The AuthMiddleware class [middleware/auth.py:15] validates JWT tokens..."
3. If the context doesn't contain the answer, say:
   "I don't have enough context to answer that. The codebase may not contain this logic."
4. Include relevant code snippets in your explanation using markdown code blocks.
5. Explain the code flow step by step — trace the execution path.
6. Be specific. Name exact functions, classes, files, and line numbers.
7. If there are multiple possible interpretations, note them.

WHAT YOU DON'T KNOW:
• You have NOT read the entire codebase — only the provided context.
• You cannot browse files, search the web, or access external information.
• If asked about code not in the context, be honest about the limitation."""


# ============================================
# Prompt Templates
# ============================================

def build_context_prompt(
    query: str,
    chunks: List[Dict],
    conversation_history: Optional[List[Dict]] = None
) -> str:
    """
    Build the complete user prompt with context and citations.
    
    Args:
        query: User's question
        chunks: Retrieved code chunks with metadata
        conversation_history: Previous exchanges (optional)
    
    Returns:
        Complete prompt string ready for the LLM
    """
    # ─── 1. Conversation History (if any) ─────────────
    history_text = ""
    if conversation_history:
        history_text = "CONVERSATION HISTORY:\n"
        for exchange in conversation_history[-6:]:  # Last 3 exchanges
            history_text += f"User: {exchange['user']}\n"
            history_text += f"Assistant: {exchange['assistant'][:300]}...\n\n"
        history_text += "─" * 40 + "\n\n"
    
    # ─── 2. Code Context ──────────────────────────────
    context_text = "CODEBASE CONTEXT:\n"
    
    for i, chunk in enumerate(chunks, 1):
        metadata = chunk.get("metadata", {})
        file = metadata.get("file", "unknown")
        start = metadata.get("start_line", "?")
        end = metadata.get("end_line", "?")
        name = metadata.get("name", "code")
        chunk_type = metadata.get("chunk_type", "function")
        
        # Citation header
        context_text += f"\n[{i}] {file}:{start}-{end} — {chunk_type} {name}\n"
        context_text += "```\n"
        context_text += chunk.get("text", "")
        context_text += "\n```\n"
        context_text += "─" * 40 + "\n"
    
    # ─── 3. Question ──────────────────────────────────
    question_text = f"\nQUESTION: {query}\n\n"
    question_text += "Explain the answer step by step, citing [file:line] for each claim."
    
    # ─── Combine ──────────────────────────────────────
    full_prompt = history_text + context_text + question_text
    
    # Log token count
    token_count = counter.count(full_prompt)
    logger.debug(f"Prompt built: {token_count} tokens ({len(chunks)} chunks)")
    
    return full_prompt


def build_simple_prompt(query: str, chunks: List[Dict]) -> str:
    """
    Simplified prompt for when token budget is tight.
    Uses shorter citations and less formatting overhead.
    """
    context_parts = []
    for i, chunk in enumerate(chunks, 1):
        metadata = chunk.get("metadata", {})
        file = metadata.get("file", "unknown")
        start = metadata.get("start_line", "?")
        name = metadata.get("name", "")
        
        context_parts.append(
            f"[{i}] {file}:{start} ({name})\n{chunk.get('text', '')}"
        )
    
    context = "\n\n".join(context_parts)
    
    return f"""CODE CONTEXT:
{context}

QUESTION: {query}

Answer citing [file:line] for each claim:"""


# ============================================
# Generator Class
# ============================================

class Generator:
    """
    Generate answers from code context using GPT-4o-mini.
    
    Features:
        • Streaming: Tokens sent one by one (feels fast)
        • Grounding: Strict rules prevent hallucination
        • Citations: Every claim backed by [file:line]
        • Conversation: Optional history for follow-up questions
    
    Usage:
        gen = Generator()
        
        # Non-streaming
        answer = gen.generate(query, chunks, history)
        
        # Streaming (for real-time UI)
        for token in gen.generate_stream(query, chunks, history):
            print(token, end="")
    """
    
    def __init__(self):
        self.client = OpenAI(api_key=OPENAI_API_KEY)
        self.model = LLM_MODEL
        
        logger.info(f"Generator initialized: model={self.model}")
    
    # ─── NON-STREAMING ────────────────────────────────
    
    def generate(
        self,
        query: str,
        chunks: List[Dict],
        conversation_history: Optional[List[Dict]] = None,
        temperature: float = 0.0
    ) -> str:
        """
        Generate a complete answer (non-streaming).
        
        Args:
            query: User's question
            chunks: Retrieved code chunks
            conversation_history: Previous exchanges
            temperature: 0.0 = deterministic, higher = creative
        
        Returns:
            Complete answer string
        """
        # Build prompt
        user_prompt = build_context_prompt(query, chunks, conversation_history)
        
        # Check token budget
        system_tokens = counter.count(SYSTEM_PROMPT)
        user_tokens = counter.count(user_prompt)
        total_tokens = system_tokens + user_tokens
        
        logger.info(f"Generating answer: {total_tokens} input tokens")
        
        # If too large, use simplified prompt
        if total_tokens > 10000:
            logger.warning(f"Prompt too large ({total_tokens} tokens), using simplified")
            user_prompt = build_simple_prompt(query, chunks)
        
        # Call LLM
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt}
            ],
            temperature=temperature,
            max_tokens=2000
        )
        
        answer = response.choices[0].message.content
        
        # Log usage
        usage = response.usage
        logger.info(
            f"Generation complete: "
            f"{usage.prompt_tokens} in / {usage.completion_tokens} out "
            f"(${counter.estimate_cost(usage.prompt_tokens, usage.completion_tokens):.4f})"
        )
        
        return answer
    
    # ─── STREAMING ────────────────────────────────────
    
    def generate_stream(
        self,
        query: str,
        chunks: List[Dict],
        conversation_history: Optional[List[Dict]] = None,
        temperature: float = 0.0
    ) -> Generator[str, None, None]:
        """
        Generate answer token by token (streaming).
        
        Yields each token as it's generated.
        The frontend displays tokens as they arrive — feels like ChatGPT.
        
        Yields:
            str: Individual tokens (words/punctuation)
        """
        # Build prompt
        user_prompt = build_context_prompt(query, chunks, conversation_history)
        
        # Check token budget
        system_tokens = counter.count(SYSTEM_PROMPT)
        user_tokens = counter.count(user_prompt)
        total_tokens = system_tokens + user_tokens
        
        if total_tokens > 10000:
            user_prompt = build_simple_prompt(query, chunks)
        
        logger.info(f"Streaming answer: ~{counter.count(user_prompt)} input tokens")
        
        # Stream from OpenAI
        stream = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt}
            ],
            temperature=temperature,
            max_tokens=2000,
            stream=True
        )
        
        # Yield tokens one by one
        for chunk in stream:
            if chunk.choices[0].delta.content:
                token = chunk.choices[0].delta.content
                yield token
    
    # ─── FULL RESPONSE WITH SOURCES ───────────────────
    
    def generate_with_sources(
        self,
        query: str,
        chunks: List[Dict],
        conversation_history: Optional[List[Dict]] = None
    ) -> Dict:
        """
        Generate answer and return with structured sources.
        
        Returns:
            {
                "answer": "The AuthMiddleware class...",
                "sources": [
                    {"file": "middleware/auth.py", "start_line": 15, ...},
                    ...
                ]
            }
        """
        # Generate answer
        answer = self.generate(query, chunks, conversation_history)
        
        # Extract sources from chunks
        sources = []
        seen_files = set()
        
        for chunk in chunks:
            metadata = chunk.get("metadata", {})
            file = metadata.get("file", "unknown")
            
            # Avoid duplicate file references
            file_key = f"{file}:{metadata.get('start_line')}"
            if file_key not in seen_files:
                seen_files.add(file_key)
                sources.append({
                    "file": file,
                    "start_line": metadata.get("start_line"),
                    "end_line": metadata.get("end_line"),
                    "function_name": metadata.get("name"),
                    "chunk_type": metadata.get("chunk_type"),
                    "relevance_score": chunk.get("rerank_score") or chunk.get("similarity")
                })
        
        return {
            "answer": answer,
            "sources": sources
        }