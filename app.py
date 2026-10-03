"""Streamlit chat UI for the LangGraph + MCP agent.
Run: streamlit run app.py
"""

import asyncio
import threading
import uuid

import streamlit as st

from agents.agent import AgentConfigError, AgentRunner
from config import settings
from mcp_app.client import MCPToolManager


st.set_page_config(
    page_title="LangGraph + MCP Agent",
    page_icon="🤖",
    layout="wide",
)


# ============================================================
# Persistent async event loop
# ============================================================

class AsyncLoopRunner:
    """Runs all async MCP/LangGraph operations on one persistent event loop."""

    def __init__(self):
        self.loop = asyncio.new_event_loop()
        self.thread = threading.Thread(
            target=self._run_loop,
            daemon=True
        )
        self.thread.start()

    def _run_loop(self):
        asyncio.set_event_loop(self.loop)
        self.loop.run_forever()

    def run(self, coro):
        future = asyncio.run_coroutine_threadsafe(coro, self.loop)
        return future.result()

    def stop(self):
        if self.loop.is_running():
            self.loop.call_soon_threadsafe(self.loop.stop)


# ============================================================
# Session initialization
# ============================================================

if "async_runner" not in st.session_state:
    st.session_state.async_runner = AsyncLoopRunner()

if "messages" not in st.session_state:
    st.session_state.messages = []

if "thread_id" not in st.session_state:
    st.session_state.thread_id = str(uuid.uuid4())

if "runner" not in st.session_state:
    st.session_state.runner = None

if "init_error" not in st.session_state:
    st.session_state.init_error = None

if "tool_info" not in st.session_state:
    st.session_state.tool_info = None


# ============================================================
# MCP + Agent initialization
# ============================================================

def init_agent(force: bool = False):
    """Discover MCP tools and build the LangGraph agent."""

    if st.session_state.runner is not None and not force:
        return

    st.session_state.runner = None
    st.session_state.init_error = None

    with st.spinner("Connecting to MCP servers and discovering tools..."):
        try:

            async_runner = st.session_state.async_runner

            # Run MCP discovery on the persistent event loop
            loaded = async_runner.run(
                MCPToolManager(
                    settings.MCP_SERVERS
                ).load_tools()
            )

            st.session_state.tool_info = loaded

            if not loaded.tools:
                st.session_state.init_error = (
                    "No MCP tools could be loaded."
                )
                return

            # AgentRunner itself is synchronous to construct
            st.session_state.runner = AgentRunner(
                loaded.tools
            )

        except AgentConfigError as exc:
            st.session_state.init_error = str(exc)

        except Exception as exc:
            st.session_state.init_error = (
                f"Startup failed: {type(exc).__name__}: {exc}"
            )


# ============================================================
# Chat reset
# ============================================================

def reset_chat():
    st.session_state.messages = []
    st.session_state.thread_id = str(uuid.uuid4())


# ============================================================
# Initialize
# ============================================================

init_agent()


# ============================================================
# Sidebar
# ============================================================

with st.sidebar:

    st.header("🧰 MCP Tools")

    info = st.session_state.get("tool_info")

    if info:

        for server, tools in info.by_server.items():

            st.markdown(f"**🟢 {server}**")

            for tool in tools:

                with st.expander(tool.name):
                    st.caption(tool.description)

        for server, err in info.errors.items():

            st.error(
                f"🔴 {server} unavailable\n\n{err[:200]}"
            )

    st.divider()

    col1, col2 = st.columns(2)

    if col1.button(
        "🗑️ Clear chat",
        use_container_width=True
    ):
        reset_chat()
        st.rerun()

    if col2.button(
        "🔄 Reload tools",
        use_container_width=True
    ):
        init_agent(force=True)
        st.rerun()

    st.caption(
        f"Model: {settings.GEMINI_MODEL}"
    )


# ============================================================
# Main UI
# ============================================================

st.title(
    "🤖 Intelligent AI Agent with LangGraph and MCP"
)

st.caption(
    "Ask in natural language - the agent picks the right MCP tool by itself."
)


if st.session_state.init_error:
    st.error(
        st.session_state.init_error
    )


# ============================================================
# Tool-call display
# ============================================================

def show_steps(steps):

    for step in steps:

        with st.expander(
            f"🔧 Tool used: {step['tool']}"
        ):

            st.markdown("**Input**")

            st.json(
                step["args"]
            )

            st.markdown("**Result**")

            st.code(
                step["result"] or "(no result)",
                language="text"
            )


# ============================================================
# Existing chat history
# ============================================================

for msg in st.session_state.messages:

    with st.chat_message(msg["role"]):

        show_steps(
            msg.get("steps", [])
        )

        if msg.get("error"):
            st.error(
                msg["content"]
            )
        else:
            st.markdown(
                msg["content"]
            )


# ============================================================
# Chat input
# ============================================================

prompt = st.chat_input(
    "Ask me anything...",
    disabled=st.session_state.runner is None
)


if prompt:

    # -------------------------------
    # User message
    # -------------------------------

    st.session_state.messages.append(
        {
            "role": "user",
            "content": prompt
        }
    )

    with st.chat_message("user"):
        st.markdown(prompt)


    # -------------------------------
    # Agent response
    # -------------------------------

    with st.chat_message("assistant"):

        with st.status(
            "Agent is reasoning and selecting tools...",
            expanded=False
        ) as status:

            try:

                # IMPORTANT:
                # Run the agent on the SAME persistent
                # event loop used for MCP discovery.

                result = st.session_state.async_runner.run(
                    st.session_state.runner.run(
                        prompt,
                        st.session_state.thread_id
                    )
                )

                if result.error:

                    status.update(
                        label="Something went wrong",
                        state="error"
                    )

                else:

                    if result.steps:

                        label = (
                            f"Used {len(result.steps)} "
                            f"tool call(s)"
                        )

                    else:

                        label = (
                            "Answered directly "
                            "(no tool needed)"
                        )

                    status.update(
                        label=label,
                        state="complete"
                    )

            except Exception as exc:

                result = None

                status.update(
                    label="Something went wrong",
                    state="error"
                )

                st.error(
                    f"Unexpected error: "
                    f"{type(exc).__name__}: {exc}"
                )


        # -------------------------------
        # Display result
        # -------------------------------

        if result is not None:

            show_steps(
                result.steps
            )

            if result.error:

                st.error(
                    result.error
                )

                assistant_content = result.error
                assistant_error = True

            else:

                st.markdown(
                    result.answer
                )

                assistant_content = result.answer
                assistant_error = False


            st.session_state.messages.append(
                {
                    "role": "assistant",
                    "steps": result.steps,
                    "content": assistant_content,
                    "error": assistant_error,
                }
            )
