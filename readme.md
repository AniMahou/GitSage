# 🧠 GitSage — Codebase Q&A Bot

**Ask questions about any GitHub repository. Get answers with exact file:line citations.**

[![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-green.svg)](https://fastapi.tiangolo.com/)
[![Streamlit](https://img.shields.io/badge/Streamlit-1.0-red.svg)](https://streamlit.io/)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

---

## 🎥 Demo

<p align="center">
  <img src="demo.gif" alt="GitSage Demo" width="800"/>
</p>

> *Paste a GitHub URL → Ask questions → Get cited answers from the actual codebase*

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

## 🏗️ Architecture
User: "How does authentication work?"
│
▼
┌──────────────────┐ ┌──────────────────┐ ┌──────────────────┐
│ Streamlit UI │───▶│ FastAPI Server │───▶│ ChromaDB │
│ (Frontend) │ │ (Backend) │ │ (Vector Store) │
└──────────────────┘ └──────────────────┘ └──────────────────┘
│
┌─────────────────────────┼─────────────────────────┐
│ │ │
▼ ▼ ▼
┌──────────────────┐ ┌──────────────────┐ ┌──────────────────┐
│ Repo Handler │ │ Code Chunker │ │ Embedder │
│ (Git Clone) │ │ (AST Parser) │ │ (MiniLM) │
└──────────────────┘ └──────────────────┘ └──────────────────┘
│
▼
┌──────────────────┐ ┌──────────────────┐
│ Retriever │───▶│ Generator │
│ (2-Stage Rank) │ │ (Groq LLM) │
└──────────────────┘ └──────────────────┘

