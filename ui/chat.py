"""Streamlit chat interface for Skillian SAP BW Assistant."""

import os

import requests
import streamlit as st

DEFAULT_BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")

# Page configuration
st.set_page_config(
    page_title="Skillian - SAP BW Assistant",
    page_icon="🔧",
    layout="wide",
)

# Initialize session state
if "messages" not in st.session_state:
    st.session_state.messages = []
if "session_id" not in st.session_state:
    st.session_state.session_id = None

# Sidebar
with st.sidebar:
    st.title("Skillian")
    st.caption("SAP BW AI Assistant")

    backend_url = st.text_input(
        "Backend URL",
        value=DEFAULT_BACKEND_URL,
        help="FastAPI backend URL",
    )

    if st.button("New Chat", use_container_width=True):
        st.session_state.messages = []
        st.session_state.session_id = None
        st.rerun()

    # Show current session
    if st.session_state.session_id:
        st.caption(f"Session: {st.session_state.session_id[:8]}...")

    st.divider()

    # Health check
    try:
        health = requests.get(f"{backend_url}/api/v1/health", timeout=2)
        if health.status_code == 200:
            data = health.json()
            st.success(f"Backend: {data.get('status', 'ok')}")
            st.caption(f"LLM: {data.get('llm_provider', 'unknown')}")
        else:
            st.error("Backend unhealthy")
    except requests.exceptions.RequestException:
        st.warning("Backend not reachable")

# Main chat area
st.header("SAP BW Assistant")

# Display chat history
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

        # Show tool calls if present
        if msg.get("tool_calls"):
            with st.expander("Tool calls", expanded=False):
                for tc in msg["tool_calls"]:
                    st.code(f"{tc['tool']}({tc['args']})\n→ {tc['result']}", language="text")

# Chat input
if prompt := st.chat_input("Ask about SAP BW data issues..."):
    # Add user message to history
    st.session_state.messages.append({"role": "user", "content": prompt})

    with st.chat_message("user"):
        st.markdown(prompt)

    # Call backend
    with st.chat_message("assistant"):
        with st.spinner("Thinking..."):
            try:
                payload = {"message": prompt}
                if st.session_state.session_id:
                    payload["session_id"] = st.session_state.session_id

                response = requests.post(
                    f"{backend_url}/api/v1/chat",
                    json=payload,
                    timeout=120,
                )

                if response.status_code == 200:
                    data = response.json()
                    assistant_message = data.get("response", "No response")
                    tool_calls = data.get("tool_calls", [])

                    # Store session_id for conversation continuity
                    if data.get("session_id"):
                        st.session_state.session_id = data["session_id"]

                    st.markdown(assistant_message)

                    # Show tool calls
                    if tool_calls:
                        with st.expander("Tool calls", expanded=False):
                            for tc in tool_calls:
                                st.code(
                                    f"{tc['tool']}({tc['args']})\n→ {tc['result']}",
                                    language="text",
                                )

                    # Save to history
                    st.session_state.messages.append(
                        {
                            "role": "assistant",
                            "content": assistant_message,
                            "tool_calls": tool_calls,
                        }
                    )
                else:
                    st.error(f"Error: {response.status_code} - {response.text}")

            except requests.exceptions.RequestException as e:
                st.error(f"Failed to connect: {e}")
