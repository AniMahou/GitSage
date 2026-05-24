# backend/core/memory.py
"""
Conversation memory for GitSage.
Manages conversation history and rewrites follow-up questions.

Why memory matters:
    User: "How does authentication work?"
    Bot:  "AuthMiddleware in middleware/auth.py:15 handles JWT..."
    User: "What happens if the token is expired?"
    
    Without memory: "What token?" — The LLM has no idea.
    With memory:    We rewrite to "What happens if the JWT token verified 
                    by verify_token in utils/jwt.py is expired?"
                    Then we search with THIS query and get relevant results.
"""

from typing import List, Dict, Optional
from openai import OpenAI

from backend.config import OPENAI_API_KEY, LLM_MODEL, MAX_CONVERSATION_TURNS
from backend.utils.logger import setup_logger

logger = setup_logger(__name__)


class ConversationMemory:
    """
    Stores and manages conversation history per session.
    
    Each session has its own conversation thread.
    History is used for:
        1. Query rewriting (make pronouns explicit)
        2. Context in the generator prompt
        3. Understanding what the user already knows
    
    Usage:
        memory = ConversationMemory()
        memory.add_exchange(session_id, user_query, assistant_response)
        rewritten = memory.rewrite_query(session_id, "What about errors?")
        history = memory.get_history(session_id)
    """
    
    def __init__(self):
        # In-memory storage: {session_id: [exchanges]}
        self._histories: Dict[str, List[Dict]] = {}
        
        # Lightweight LLM client for query rewriting
        self.client = OpenAI(api_key=OPENAI_API_KEY)
        
        logger.info("ConversationMemory initialized")
    
    # ─── HISTORY MANAGEMENT ───────────────────────────
    
    def add_exchange(
        self,
        session_id: str,
        user_query: str,
        assistant_response: str
    ):
        """
        Add a Q&A exchange to the conversation history.
        
        Args:
            session_id: Session identifier
            user_query: What the user asked
            assistant_response: What the bot answered
        """
        # Initialize history if new session
        if session_id not in self._histories:
            self._histories[session_id] = []
        
        # Add exchange
        self._histories[session_id].append({
            "user": user_query,
            "assistant": assistant_response
        })
        
        # Trim to max turns (keep most recent)
        if len(self._histories[session_id]) > MAX_CONVERSATION_TURNS:
            self._histories[session_id] = self._histories[session_id][-MAX_CONVERSATION_TURNS:]
        
        logger.debug(
            f"Memory: Session {session_id[:8]} now has "
            f"{len(self._histories[session_id])} exchanges"
        )
    
    def get_history(
        self,
        session_id: str,
        last_n: int = None
    ) -> List[Dict]:
        """
        Get conversation history for a session.
        
        Args:
            session_id: Session identifier
            last_n: Return only the last N exchanges (default: all)
        
        Returns:
            List of {"user": "...", "assistant": "..."} dicts
        """
        history = self._histories.get(session_id, [])
        
        if last_n and len(history) > last_n:
            return history[-last_n:]
        
        return history
    
    def clear_history(self, session_id: str):
        """Clear conversation history for a session."""
        if session_id in self._histories:
            del self._histories[session_id]
            logger.info(f"Memory cleared for session {session_id[:8]}")
    
    def has_history(self, session_id: str) -> bool:
        """Check if a session has any conversation history."""
        return session_id in self._histories and len(self._histories[session_id]) > 0
    
    def get_turn_count(self, session_id: str) -> int:
        """Get number of exchanges in a session."""
        return len(self._histories.get(session_id, []))
    
    # ─── QUERY REWRITING ─────────────────────────────
    
    def rewrite_query(self, session_id: str, query: str) -> str:
        """
        Rewrite a follow-up question using conversation history.
        
        This is the KEY to making follow-up questions work.
        
        Examples:
            History: User asked about "authentication middleware"
            Query: "What about errors?"
            Rewritten: "How does the authentication middleware handle errors?"
            
            History: User asked about "Session class in requests library"
            Query: "What does the request method do?"
            Rewritten: "What does the Session.request method do in the requests library?"
        
        Args:
            session_id: Session identifier
            query: User's raw follow-up question
        
        Returns:
            Standalone query that doesn't depend on conversation history
        """
        # If no history, return as-is
        if not self.has_history(session_id):
            return query
        
        # If query is already specific enough, return as-is
        if self._is_standalone(query):
            logger.debug(f"Query already standalone: '{query[:60]}...'")
            return query
        
        # Build context from history
        history = self.get_history(session_id, last_n=3)
        history_text = self._format_history_for_rewrite(history)
        
        # Call LLM to rewrite
        logger.debug(f"Rewriting query: '{query[:60]}...'")
        
        try:
            rewritten = self._llm_rewrite(history_text, query)
            logger.debug(f"Rewritten to: '{rewritten[:80]}...'")
            return rewritten
        except Exception as e:
            logger.warning(f"Query rewrite failed: {e}. Using original query.")
            return query
    
    def _is_standalone(self, query: str) -> bool:
        """
        Check if a query is likely standalone (doesn't need rewriting).
        
        Signs of a standalone query:
        • Contains specific function/class/file names
        • Long enough to be self-contained
        • Starts with "How", "What", "Explain", "Show me"
        
        Signs of a follow-up (needs rewriting):
        • Contains pronouns: "it", "that", "this", "they"
        • Short and vague: "Why?", "How?", "Errors?"
        • References previous context: "the above", "that function"
        """
        # If it's very short and vague
        if len(query.split()) <= 3:
            return False
        
        # If it contains unresolved pronouns
        followup_indicators = [
            " it ", " that ", " this ", " they ", " them ",
            " the above ", " that function ", " that class ",
            " those ", " these ", " its "
        ]
        
        query_lower = f" {query.lower()} "
        for indicator in followup_indicators:
            if indicator in query_lower:
                return False
        
        return True
    
    def _format_history_for_rewrite(self, history: List[Dict]) -> str:
        """Format conversation history for the rewrite prompt."""
        lines = []
        for i, exchange in enumerate(history, 1):
            lines.append(f"Turn {i}:")
            lines.append(f"User: {exchange['user']}")
            # Truncate assistant response for the rewrite prompt
            assistant_short = exchange['assistant'][:300]
            if len(exchange['assistant']) > 300:
                assistant_short += "..."
            lines.append(f"Assistant: {assistant_short}")
            lines.append("")
        
        return "\n".join(lines)
    
    def _llm_rewrite(self, history_text: str, query: str) -> str:
        """
        Use a lightweight LLM call to rewrite the query.
        
        This is a SMALL, FAST call — not the full generation.
        We use gpt-4o-mini for this because:
        • It's cheap ($0.15/1M input tokens)
        • It's fast (~200ms)
        • The task is simple (pronoun resolution)
        """
        prompt = f"""You are a query rewriter. Based on the conversation history, 
rewrite the user's follow-up question into a COMPLETE, STANDALONE question.

Rules:
- Resolve all pronouns (it, that, this, they) to their actual referents
- Include specific function/class/file names from the history
- Make the question self-contained — someone reading it without history should understand
- Do NOT answer the question — just rewrite it
- Keep it concise (one sentence)

CONVERSATION HISTORY:
{history_text}

FOLLOW-UP QUESTION: {query}

STANDALONE QUESTION:"""

        response = self.client.chat.completions.create(
            model=LLM_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
            max_tokens=150
        )
        
        rewritten = response.choices[0].message.content.strip()
        
        # Remove quotes if the LLM wrapped it in them
        if rewritten.startswith('"') and rewritten.endswith('"'):
            rewritten = rewritten[1:-1]
        
        return rewritten
    
    # ─── CONTEXT FOR GENERATOR ─────────────────────────
    
    def get_context_for_generator(
        self,
        session_id: str,
        max_exchanges: int = 3
    ) -> Optional[List[Dict]]:
        """
        Get conversation history formatted for the generator prompt.
        
        Returns None if no history exists, so the generator knows
        this is a first question.
        """
        if not self.has_history(session_id):
            return None
        
        return self.get_history(session_id, last_n=max_exchanges)
    
    # ─── STATS & DEBUG ─────────────────────────────────
    
    def get_stats(self) -> Dict:
        """Get memory statistics across all sessions."""
        total_sessions = len(self._histories)
        total_exchanges = sum(len(h) for h in self._histories.values())
        
        return {
            "active_conversations": total_sessions,
            "total_exchanges": total_exchanges,
            "avg_exchanges_per_session": (
                total_exchanges / total_sessions if total_sessions > 0 else 0
            )
        }
    
    def debug_print_history(self, session_id: str):
        """Print conversation history for debugging."""
        history = self.get_history(session_id)
        
        if not history:
            print("(No history)")
            return
        
        print(f"\n📜 Conversation History ({len(history)} exchanges):")
        print("=" * 50)
        
        for i, exchange in enumerate(history, 1):
            print(f"\n--- Turn {i} ---")
            print(f"👤 User: {exchange['user']}")
            print(f"🤖 Assistant: {exchange['assistant'][:200]}...")
        
        print("=" * 50)