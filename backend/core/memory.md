┌─────────────────────────────────────────────────────────────────┐
│                     MEMORY — Full Flow                           │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  TURN 1 (First Question):                                       │
│  ─────────────────────────                                      │
│  User: "How does authentication work?"                          │
│       │                                                          │
│       ▼                                                          │
│  rewrite_query() → "How does authentication work?"              │
│  (No history → return as-is)                                    │
│       │                                                          │
│       ▼                                                          │
│  Search with this query → Retrieve chunks → Generate answer     │
│       │                                                          │
│       ▼                                                          │
│  add_exchange(                                                   │
│    user="How does authentication work?",                         │
│    assistant="AuthMiddleware in middleware/auth.py:15 handles..." │
│  )                                                               │
│                                                                  │
│  History: [Exchange 1]                                           │
│                                                                  │
│  ═══════════════════════════════════════════════════════════    │
│                                                                  │
│  TURN 2 (Follow-up):                                            │
│  ────────────────────                                            │
│  User: "What happens if the token is expired?"                  │
│       │                                                          │
│       ▼                                                          │
│  _is_standalone() → FALSE                                       │
│  (Contains "the token" — unresolved reference!)                 │
│       │                                                          │
│       ▼                                                          │
│  _llm_rewrite(history, query):                                  │
│    Input:                                                        │
│      History: "User asked about authentication middleware"      │
│      Query: "What happens if the token is expired?"             │
│    Output:                                                       │
│      "What happens if the JWT token verified by verify_token    │
│       in utils/jwt.py is expired?"                              │
│       │                                                          │
│       ▼                                                          │
│  Search with REWRITTEN query → Retrieve RELEVANT chunks         │
│  (Finds utils/jwt.py instead of random "token" mentions)        │
│       │                                                          │
│       ▼                                                          │
│  Generate answer WITH conversation history in the prompt         │
│  (LLM sees both "the user previously asked about auth"          │
│   AND the new chunks about JWT expiration)                       │
│       │                                                          │
│       ▼                                                          │
│  add_exchange(...) → History: [Exchange 1, Exchange 2]          │
│                                                                  │
│  ═══════════════════════════════════════════════════════════    │
│                                                                  │
│  TURN 12 (Memory Limit):                                        │
│  ─────────────────────────                                       │
│  History has 12 exchanges → MAX_CONVERSATION_TURNS = 10          │
│  Oldest 2 exchanges are DROPPED                                  │
│  History: [Exchange 3, 4, 5, 6, 7, 8, 9, 10, 11, 12]          │
│                                                                  │
│  Why drop old ones?                                              │
│  • Cost: Each exchange adds ~200-500 tokens to prompt            │
│  • "Lost in the Middle": LLM pays less attention to old history  │
│  • Relevance: Very old exchanges are less relevant               │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘