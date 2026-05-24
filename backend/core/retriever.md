┌─────────────────────────────────────────────────────────────────┐
│                 TWO-STAGE RETRIEVAL — Full Flow                  │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  User asks: "How does the authentication middleware work?"       │
│       │                                                          │
│       ▼                                                          │
│  ╔═════════════════════════════════════════════════════════════╗  │
│  ║  STAGE 1: Embedding Search (Fast, Coarse)                   ║  │
│  ╠═════════════════════════════════════════════════════════════╣  │
│  ║                                                             ║  │
│  ║  1. Embed query → [0.031, -0.089, 0.142, ...]              ║  │
│  ║                                                             ║  │
│  ║  2. Search ChromaDB (HNSW index)                            ║  │
│  ║     • 1,247 chunks in collection                            ║  │
│  ║     • HNSW navigates graph structure                        ║  │
│  ║     • Compares query vector to ~50 chunks (not all 1,247)   ║  │
│  ║     • Returns 20 most similar                               ║  │
│  ║                                                             ║  │
│  ║  Time: ~5ms                                                 ║  │
│  ║                                                             ║  │
│  ║  Result: 20 candidates with similarity scores               ║  │
│  ║  ┌──────┬──────────────────────────────────┬──────────┐    ║  │
│  ║  │ Rank │ Chunk                            │ Sim      │    ║  │
│  ║  ├──────┼──────────────────────────────────┼──────────┤    ║  │
│  ║  │  1   │ class AuthMiddleware...          │ 0.87     │    ║  │
│  ║  │  2   │ def verify_token...              │ 0.83     │    ║  │
│  ║  │  3   │ class EmailSender...             │ 0.81     │    ║  │
│  ║  │  4   │ def login_required...            │ 0.79     │    ║  │
│  ║  │ ...  │ ...                              │ ...      │    ║  │
│  ║  │ 20   │ def send_notification...         │ 0.65     │    ║  │
│  ║  └──────┴──────────────────────────────────┴──────────┘    ║  │
│  ╚═════════════════════════════════════════════════════════════╝  │
│       │                                                          │
│       │ 20 candidates                                            │
│       ▼                                                          │
│  ╔═════════════════════════════════════════════════════════════╗  │
│  ║  STAGE 2: Cross-Encoder Rerank (Slow, Precise)              ║  │
│  ╠═════════════════════════════════════════════════════════════╣  │
│  ║                                                             ║  │
│  ║  For EACH of 20 candidates:                                 ║  │
│  ║    Input: [query, chunk_text]                               ║  │
│  ║    Cross-encoder reads BOTH simultaneously                  ║  │
│  ║    Output: Relevance score (0.0 to ~1.0)                    ║  │
│  ║                                                             ║  │
│  ║  Time: ~300ms total (20 pairs × ~15ms each)                 ║  │
│  ║                                                             ║  │
│  ║  Reranked Result (top 5):                                   ║  │
│  ║  ┌──────┬──────────────────────────────────┬──────────┐    ║  │
│  ║  │ Rank │ Chunk                            │ Rerank   │    ║  │
│  ║  ├──────┼──────────────────────────────────┼──────────┤    ║  │
│  ║  │  1   │ class AuthMiddleware...          │ 0.94  ↑  │    ║  │
│  ║  │  2   │ def login_required...            │ 0.89  ↑  │    ║  │
│  ║  │  3   │ def verify_token...              │ 0.85  ↓  │    ║  │
│  ║  │  4   │ JWT_SECRET = os.environ...       │ 0.78  ↑  │    ║  │
│  ║  │  5   │ class Session...                 │ 0.74  ↑  │    ║  │
│  ║  └──────┴──────────────────────────────────┴──────────┘    ║  │
│  ║                                                             ║  │
│  ║  Notice:                                                    ║  │
│  ║  • EmailSender DROPPED (was #3, now gone — correct!)       ║  │
│  ║  • login_required MOVED UP (was #4, now #2 — correct!)     ║  │
│  ║  • JWT_SECRET ADDED (was #11, now #4 — correct!)           ║  │
│  ╚═════════════════════════════════════════════════════════════╝  │
│       │                                                          │
│       ▼                                                          │
│  Output: Top 5 most relevant chunks → sent to generator.py      │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘