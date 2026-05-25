# frontend/app.py
"""
GitSage — Minimal Streamlit Frontend
Single page: Input GitHub URL → Ask questions → Get answers
"""

import streamlit as st
import requests
import time
import json

# ============================================
# CONFIG
# ============================================
st.set_page_config(
    page_title="GitSage",
    page_icon="",
    layout="wide"
)

API_URL = "http://127.0.0.1:8000"

# ============================================
# SESSION STATE
# ============================================
if "session_id" not in st.session_state:
    st.session_state.session_id = None
if "status" not in st.session_state:
    st.session_state.status = None
if "messages" not in st.session_state:
    st.session_state.messages = []

# ============================================
# HEADER
# ============================================
st.title("GitSage")
st.caption("Ask questions about any GitHub repository")

# ============================================
# SIDEBAR — Repo Input
# ============================================
with st.sidebar:
    st.header("📂 Repository")
    
    repo_url = st.text_input(
        "GitHub URL",
        placeholder="https://github.com/user/repo"
    )
    
    if st.button("🔍 Index Repository", type="primary", use_container_width=True):
        if repo_url:
            with st.spinner("Creating session..."):
                # Create session
                resp = requests.post(
                    f"{API_URL}/api/sessions",
                    json={"repo_url": repo_url}
                )
                if resp.ok:
                    data = resp.json()
                    st.session_state.session_id = data["session_id"]
                    st.session_state.status = "indexing"
                    st.session_state.messages = []
                    
                    # Start indexing
                    requests.post(
                        f"{API_URL}/api/sessions/{st.session_state.session_id}/index"
                    )
                    st.rerun()
                else:
                    st.error(f"Failed: {resp.json().get('detail', 'Unknown error')}")
        else:
            st.warning("Enter a GitHub URL")
    
    # Show status
    if st.session_state.session_id:
        st.divider()
        st.header("📊 Status")
        
        # Poll status
        if st.session_state.status in ("indexing", "cloning", "parsing", "embedding"):
            resp = requests.get(
                f"{API_URL}/api/sessions/{st.session_state.session_id}"
            )
            if resp.ok:
                data = resp.json()
                st.session_state.status = data["status"]
                
                if data["status"] == "ready":
                    st.success(f"✅ {data['progress']}")
                    st.metric("Chunks", data["chunks_indexed"])
                    st.metric("Files", data["files_found"])
                    st.rerun()
                elif data["status"] == "error":
                    st.error(f"❌ {data.get('error_message', 'Unknown error')}")
                else:
                    st.info(f"⏳ {data.get('progress', 'Processing...')}")
                    time.sleep(2)
                    st.rerun()
        elif st.session_state.status == "ready":
            st.success("✅ Ready")
        elif st.session_state.status == "error":
            st.error("❌ Indexing failed")
    
    # Settings
    if st.session_state.status == "ready":
        st.divider()
        st.header("⚙️ Settings")
        k_chunks = st.slider("Chunks to retrieve", 1, 10, 5)

# ============================================
# MAIN — Chat Area
# ============================================

if st.session_state.status != "ready":
    st.info("👈 Enter a GitHub URL in the sidebar to get started")
else:
    # Display chat history
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])
            if msg.get("sources"):
                with st.expander("📚 Sources"):
                    for src in msg["sources"]:
                        file_name = src["file"].split("/")[-1]
                        st.caption(
                            f"• `{file_name}:{src['start_line']}` "
                            f"({src.get('function_name', 'unknown')}) "
                            f"[score: {src.get('relevance_score', 0):.2f}]"
                        )
    
    # Chat input
    query = st.chat_input("Ask about the codebase...")
    
    if query:
        # Add user message
        st.session_state.messages.append({"role": "user", "content": query})
        with st.chat_message("user"):
            st.markdown(query)
        
        # Get answer
        with st.chat_message("assistant"):
            with st.spinner("Thinking..."):
                resp = requests.post(
                    f"{API_URL}/api/sessions/{st.session_state.session_id}/query/sync",
                    json={
                        "session_id": st.session_state.session_id,
                        "query": query
                    }
                )
                
                if resp.ok:
                    data = resp.json()
                    answer = data["answer"]
                    sources = data.get("sources", [])
                    
                    st.markdown(answer)
                    
                    if sources:
                        with st.expander("📚 Sources"):
                            for src in sources:
                                file_name = src["file"].split("/")[-1]
                                st.caption(
                                    f"• `{file_name}:{src['start_line']}` "
                                    f"({src.get('function_name', 'unknown')})"
                                )
                    
                    # Store in history
                    st.session_state.messages.append({
                        "role": "assistant",
                        "content": answer,
                        "sources": sources
                    })
                else:
                    st.error(f"Error: {resp.json().get('detail', 'Unknown')}")