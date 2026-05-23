codebase-qa-bot/
│
├── backend/                          # All server-side logic
│   ├── __init__.py                   # Makes backend a Python package
│   ├── main.py                       # FastAPI app — entry point
│   ├── config.py                     # Settings, API keys, constants
│   │
│   ├── models/                       # Data structures (schemas)
│   │   ├── __init__.py
│   │   └── schemas.py                # Pydantic models for API
│   │
│   ├── core/                         # Business logic (the brain)
│   │   ├── __init__.py
│   │   ├── repo_handler.py           # Git clone, ZIP extract, file walk
│   │   ├── chunker.py                # AST parsing, code chunking
│   │   ├── embedder.py               # OpenAI embedding calls
│   │   ├── retriever.py              # Vector search + rerank
│   │   ├── generator.py              # LLM answer generation
│   │   └── memory.py                 # Conversation history management
│   │
│   ├── db/                           # Database operations
│   │   ├── __init__.py
│   │   ├── vector_store.py           # ChromaDB CRUD operations
│   │   └── session_store.py          # Session metadata (JSON/SQLite)
│   │
│   └── utils/                        # Helpers
│       ├── __init__.py
│       ├── logger.py                 # Logging setup
│       └── token_counter.py          # Token counting & budget
│
├── frontend/                         # User interface
│   ├── app.py                        # Streamlit entry point
│   ├── components/
│   │   ├── __init__.py
│   │   ├── chat.py                   # Chat message display
│   │   ├── sidebar.py                # Repo input, settings panel
│   │   └── source_viewer.py          # Code snippet display
│   └── utils/
│       ├── __init__.py
│       └── api_client.py             # HTTP calls to backend
│
├── data/                             # Runtime data (gitignored)
│   ├── repos/                        # Cloned repositories
│   │   └── {session_id}/             # One folder per session
│   └── chroma_db/                    # Vector database files
│       └── {collection_name}/        # One collection per session
│
├── tests/                            # Test files
│   ├── __init__.py
│   ├── test_chunker.py               # Chunker unit tests
│   ├── test_retriever.py             # Retrieval tests
│   ├── test_repo_handler.py          # Repo handler tests
│   └── test_api.py                   # API integration tests
│
├── scripts/                          # Utility scripts
│   └── cleanup_sessions.py           # Delete old sessions
│
├── requirements.txt                  # Python dependencies
├── .env.example                      # Template for environment variables
├── .gitignore                        # Files to exclude from git
├── Dockerfile                        # Container definition
├── docker-compose.yml                # Multi-service orchestration
└── README.md                         # Project documentation