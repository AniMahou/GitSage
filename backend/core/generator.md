┌─────────────────────────────────────────────────────────────────┐
│                     GENERATOR — Full Flow                        │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Input: query + 5 chunks + conversation history                  │
│       │                                                          │
│       ▼                                                          │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │  BUILD PROMPT                                            │    │
│  │                                                          │    │
│  │  SYSTEM: "You are an expert code reviewer..."            │    │
│  │                                                          │    │
│  │  HISTORY: (if follow-up question)                        │    │
│  │    User: How does auth work?                             │    │
│  │    Assistant: AuthMiddleware handles...                  │    │
│  │                                                          │    │
│  │  CONTEXT:                                                │    │
│  │    [1] middleware/auth.py:15-47 — class AuthMiddleware   │    │
│  │    ```                                                   │    │
│  │    class AuthMiddleware:                                 │    │
│  │        def process(self, request):                       │    │
│  │            token = request.headers.get('Authorization')  │    │
│  │            ...                                           │    │
│  │    ```                                                   │    │
│  │                                                          │    │
│  │    [2] utils/jwt.py:42-68 — def verify_token             │    │
│  │    ```                                                   │    │
│  │    def verify_token(token):                              │    │
│  │        return jwt.decode(token, JWT_SECRET)              │    │
│  │    ```                                                   │    │
│  │    ... (3 more chunks)                                   │    │
│  │                                                          │    │
│  │  QUESTION: How does authentication work?                 │    │
│  │  Explain step by step, citing [file:line].               │    │
│  └─────────────────────────────────────────────────────────┘    │
│       │                                                          │
│       ▼                                                          │
│  ┌─────────────────┐                                             │
│  │  Check Budget    │  Is prompt > 10K tokens?                   │
│  │                  │  Yes → Use simplified prompt               │
│  │                  │  No  → Continue                            │
│  └────────┬────────┘                                             │
│           │                                                      │
│           ▼                                                      │
│  ┌─────────────────┐                                             │
│  │  Call LLM       │  GPT-4o-mini                                │
│  │                  │  temperature=0.0 (no creativity)           │
│  │                  │  max_tokens=2000                           │
│  │                  │  stream=True (if streaming)                │
│  └────────┬────────┘                                             │
│           │                                                      │
│     ┌─────┴─────┐                                                │
│     │           │                                                │
│     ▼           ▼                                                │
│  Streaming   Non-streaming                                       │
│  Token by    Complete answer                                      │
│  token       all at once                                          │
│     │           │                                                │
│     └─────┬─────┘                                                │
│           │                                                      │
│           ▼                                                      │
│  Output: Answer with [file:line] citations                       │
│                                                                  │
│  "The authentication flow works as follows:                      │
│                                                                  │
│   1. **AuthMiddleware** [middleware/auth.py:15] intercepts        │
│      every incoming request...                                   │
│                                                                  │
│   2. It extracts the JWT token from the Authorization header     │
│      [middleware/auth.py:25]:                                    │
│      `token = request.headers.get('Authorization')`              │
│                                                                  │
│   3. The token is verified using **verify_token**                │
│      [utils/jwt.py:42] which decodes it with the JWT_SECRET..."  │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘