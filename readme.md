# 🧠 GitSage — Codebase Q&A Bot

**Ask questions about any GitHub repository. Get answers with exact file:line citations.**

---

## 🧠 What It Does

GitSage is a **Retrieval Augmented Generation (RAG)** system specialized for codebases. It:

1. **Clones** any public GitHub repository
2. **Parses** the code using AST (Abstract Syntax Tree) — understands functions, classes, and methods
3. **Embeds** every code chunk into a vector database using semantic embeddings
4. **Retrieves** the most relevant code when you ask a question (two-stage: embedding search + cross-encoder reranking)
5. **Generates** a clear, cited answer using Groq's Llama 3.3 70B (free)

Every answer includes **[file:line]** citations pointing to the exact code.

---

## ✨ Features

- 🔍 **Semantic Code Search** — Find code by meaning, not keywords
- 📎 **File:Line Citations** — Every claim backed by exact source location
- 💬 **Conversation Memory** — Ask follow-up questions naturally
- 🌐 **Multi-Language** — Python, JavaScript, C++, Go, Rust, and more
- 🆓 **100% Free** — Uses Groq (free LLM) + local embeddings
- ⚡ **Two-Stage Retrieval** — Embedding search + cross-encoder rerank
- 🧩 **AST-Aware Chunking** — Splits code by functions, not characters

---

## 🏗️ Architecture

(ARCHITECTURE_DIAGRAM_GOES_HERE)

### Retrieval Pipeline (Two-Stage)

| Stage | Method | Speed | Accuracy |
|:------|:-------|:------|:---------|
| **Stage 1** | Embedding Search (Cosine Similarity) | ~5ms | Finds 20 candidates |
| **Stage 2** | Cross-Encoder Rerank (ms-marco-MiniLM) | ~300ms | Reranks to top 5 |

---

## 🚀 Quick Start

### Prerequisites

- Python 3.10+
- Git installed on your system
- Groq API key (get one free at console.groq.com/keys)

### 1. Clone the Repository

```bash
git clone https://github.com/yourusername/GitSage.git
cd GitSage 
```
### 2. Install Dependencies

```bash
pip install -r requirements.txt
```
### 3. Configure Environment

```bash
cp .env.example .env
```

Edit .env and add your Groq API key:
```bash
GROQ_API_KEY=gsk_your_actual_key_here
```

### 4. Start the backend
```bash
python -m backend.main
```
API live at http://localhost:8000 | Docs at http://localhost:8000/docs

### 5. Start the Frontend (New Terminal)
```bash
cd frontend
python3 -m streamlit run app.py
```
UI opens at http://localhost:8501

### 6. Use GitSage
Paste a GitHub URL in the sidebar

Click "Index Repository" — wait 30-60 seconds

Ask questions in the chat

---

## 🧪 API Endpoints

| Method | Endpoint | Description |
|:-------|:---------|:------------|
| `POST` | `/api/sessions` | Create a new session |
| `POST` | `/api/sessions/{id}/index` | Index a repository |
| `GET` | `/api/sessions/{id}` | Get session status |
| `POST` | `/api/sessions/{id}/query/sync` | Ask a question |
| `DELETE` | `/api/sessions/{id}` | Delete a session |
| `GET` | `/api/health` | Health check |

---

## 🔧 Tech Stack

| Layer | Technology | Purpose |
|:------|:-----------|:--------|
| **Frontend** | Streamlit | Chat UI |
| **Backend** | FastAPI | API server |
| **LLM** | Groq (Llama 3.3 70B) | Answer generation (free) |
| **Embeddings** | all-MiniLM-L6-v2 | Local vector embeddings (free) |
| **Vector DB** | ChromaDB | Semantic search |
| **Reranker** | ms-marco-MiniLM-L-6-v2 | Cross-encoder reranking |
| **Code Parsing** | AST (built-in) | Python code chunking |
| **Git** | GitPython | Repository cloning |

---

## 💰 Cost

**$0.00** — Entirely free to run.

- Groq API: Free tier (generous rate limits)
- Embeddings: Local model (no API calls)
- ChromaDB: Local storage (no cloud costs)

---

## 📁 Project Structure
GitSage/
├── backend/
│ ├── main.py # FastAPI server
│ ├── config.py # Configuration
│ ├── models/
│ │ └── schemas.py # Pydantic models
│ ├── core/
│ │ ├── repo_handler.py # Git clone & file walk
│ │ ├── chunker.py # AST-based code chunking
│ │ ├── embedder.py # Local embedding generation
│ │ ├── retriever.py # Two-stage retrieval
│ │ ├── generator.py # Groq LLM generation
│ │ └── memory.py # Conversation history
│ ├── db/
│ │ ├── vector_store.py # ChromaDB operations
│ │ └── session_store.py # Session management
│ └── utils/
│ ├── logger.py # Logging
│ └── token_counter.py # Token management
├── frontend/
│ └── app.py # Streamlit UI
├── .env.example
├── requirements.txt
└── README.md


---

## 🎯 Example Queries

Try these on the `requests` library or any repo:

```bash 
"How does the Session class handle authentication?"
"What happens when a request times out?"
"How are redirects followed?"
"Explain the connection pooling mechanism"
```


---

## 📝 License

MIT License — feel free to use, modify, and distribute.

---

## 🙏 Acknowledgments

- [Groq](https://groq.com) for free LLM inference
- [Sentence Transformers](https://sbert.net) for local embeddings
- [ChromaDB](https://trychroma.com) for the vector database
- [LangChain](https://langchain.com) for text splitting utilities










