"""Streamlit chat UI for the LangGraph + MCP agent. Run: streamlit run app.py"""
import asyncio
import uuid

import streamlit as st

from agents.agent import AgentConfigError, AgentRunner
from config import settings
from mcp_app.client import MCPToolManager

st.set_page_config(page_title="LangGraph + MCP Agent", page_icon="🤖", layout="wide")


def init_agent(force: bool = False):
    """Discover MCP tools and build the LangGraph agent (once per session)."""
    if "runner" in st.session_state and not force:
        return
    st.session_state.runner = None
    st.session_state.init_error = None
    with st.spinner("Connecting to MCP servers and discovering tools..."):
        try:
            loaded = asyncio.run(MCPToolManager(settings.MCP_SERVERS).load_tools())
            st.session_state.tool_info = loaded
            if not loaded.tools:
                st.session_state.init_error = "No MCP tools could be loaded."
            st.session_state.runner = AgentRunner(loaded.tools)
        except AgentConfigError as exc:
            st.session_state.init_error = str(exc)
        except Exception as exc:
            st.session_state.init_error = f"Startup failed: {type(exc).__name__}: {exc}"


def reset_chat():
    st.session_state.messages = []
    st.session_state.thread_id = str(uuid.uuid4())  # new thread = fresh memory


# ---- session state ----
if "messages" not in st.session_state:
    reset_chat()
init_agent()

# ---- sidebar ----
with st.sidebar:
    st.header("🧰 MCP Tools")
    info = st.session_state.get("tool_info")
    if info:
        for server, tools in info.by_server.items():
            st.markdown(f"**🟢 {server}**")
            for t in tools:
                with st.expander(t.name):
                    st.caption(t.description)
        for server, err in info.errors.items():
            st.error(f"🔴 {server} unavailable\n\n{err[:200]}")
    st.divider()
    col1, col2 = st.columns(2)
    if col1.button("🗑️ Clear chat", use_container_width=True):
        reset_chat()
        st.rerun()
    if col2.button("🔄 Reload tools", use_container_width=True):
        init_agent(force=True)
        st.rerun()
    st.caption(f"Model: {settings.GEMINI_MODEL}")

# ---- main area ----
st.title("🤖 Intelligent AI Agent with LangGraph and MCP")
st.caption("Ask in natural language - the agent picks the right MCP tool by itself.")

if st.session_state.init_error:
    st.error(st.session_state.init_error)


def show_steps(steps):
    for s in steps:
        with st.expander(f"🔧 Tool used: {s['tool']}"):
            st.markdown("**Input**")
            st.json(s["args"])
            st.markdown("**Result**")
            st.code(s["result"] or "(no result)", language="text")


for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        show_steps(msg.get("steps", []))
        if msg.get("error"):
            st.error(msg["content"])
        else:
            st.markdown(msg["content"])

prompt = st.chat_input("Ask me anything...", disabled=st.session_state.runner is None)
if prompt:
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)
    with st.chat_message("assistant"):
        with st.status("Agent is reasoning and selecting tools...", expanded=False) as status:
            result = asyncio.run(
                st.session_state.runner.run(prompt, st.session_state.thread_id))
            if result.error:
                status.update(label="Something went wrong", state="error")
            else:
                label = (f"Used {len(result.steps)} tool call(s)" if result.steps
                         else "Answered directly (no tool needed)")
                status.update(label=label, state="complete")
        show_steps(result.steps)
        if result.error:
            st.error(result.error)
        else:
            st.markdown(result.answer)
    st.session_state.messages.append({
        "role": "assistant", "steps": result.steps,
        "content": result.error or result.answer, "error": bool(result.error)})
