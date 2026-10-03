"""LangGraph ReAct agent.

Graph:
    START -> agent -> guarded_tools -> agent -> ... -> END

The guarded tool node prevents repeated web_search calls within
the same user request while allowing other tools to work normally.
"""

from dataclasses import dataclass, field
from typing import Annotated, TypedDict

from langchain_core.messages import (
    AIMessage,
    AnyMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode, tools_condition

from config import settings


SYSTEM_PROMPT = """You are a helpful AI assistant with access to external tools via MCP.

- Decide whether a tool is needed.
- Use tools for arithmetic, current weather, current time, live web information,
  and company database questions.
- Answer general knowledge or conversational questions directly WITHOUT tools.

WEB SEARCH RULES:
- For a web-search request, call web_search when current or external information
  is required.
- Make at most ONE web_search call for the current user request.
- After receiving web search results, answer using those results directly.
- NEVER call web_search again after already receiving search results.
- Do NOT repeat or refine the same search just because the results are imperfect.
- Do NOT call web_search multiple times for the same question.
- If search results are available, use them and provide the best answer possible.
- If the search returns SEARCH_ERROR or NO_RESULTS, explain the problem instead
  of repeatedly searching.

OTHER TOOLS:
- Use calculator for arithmetic.
- Use weather for current weather.
- Use datetime for current time or time conversion.
- Use database tools for company database questions.

- If the user's question is ambiguous, ask a concise clarification when necessary.
- Use earlier messages in the conversation to resolve follow-up questions.
- Be concise and friendly.
"""


class AgentConfigError(Exception):
    """Raised for setup problems such as a missing API key."""


class AgentState(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]


@dataclass
class AgentResult:
    answer: str
    steps: list[dict] = field(default_factory=list)
    error: str | None = None


def _text(content) -> str:
    """Gemini may return a string or a list of content blocks."""
    if isinstance(content, str):
        return content

    parts = []

    for block in content or []:
        if isinstance(block, str):
            parts.append(block)

        elif isinstance(block, dict) and block.get("type") == "text":
            parts.append(block.get("text", ""))

    return "".join(parts)


def build_graph(tools):

    if not settings.GOOGLE_API_KEY:
        raise AgentConfigError(
            "GOOGLE_API_KEY is missing. Add it to your .env file."
        )

    llm = ChatGoogleGenerativeAI(
        model=settings.GEMINI_MODEL,
        google_api_key=settings.GOOGLE_API_KEY,
        temperature=settings.LLM_TEMPERATURE,
    )

    llm_with_tools = llm.bind_tools(tools) if tools else llm

    # ---------------------------------------------------------
    # Agent node
    # ---------------------------------------------------------

    async def agent_node(state: AgentState):

        messages = [
            SystemMessage(content=SYSTEM_PROMPT)
        ] + state["messages"]

        response = await llm_with_tools.ainvoke(messages)

        return {
            "messages": [response]
        }

    # ---------------------------------------------------------
    # Guarded tool node
    # ---------------------------------------------------------

    normal_tool_node = ToolNode(
        tools,
        handle_tool_errors=True,
    )

    async def guarded_tool_node(state: AgentState):

        messages = state["messages"]

        if not messages:
            return {"messages": []}

        last_message = messages[-1]

        if not isinstance(last_message, AIMessage):
            return {"messages": []}

        tool_calls = last_message.tool_calls

        if not tool_calls:
            return {"messages": []}

        # -----------------------------------------------------
        # Detect web_search calls already made in THIS turn.
        # -----------------------------------------------------

        web_search_already_used = False

        # Walk backwards through the current graph state.
        # Stop when we reach the latest HumanMessage.
        for msg in reversed(messages[:-1]):

            if isinstance(msg, HumanMessage):
                break

            if isinstance(msg, ToolMessage):

                # Find the tool name corresponding to this ToolMessage.
                for previous_msg in reversed(messages):

                    if isinstance(previous_msg, AIMessage):

                        for call in previous_msg.tool_calls:

                            if call["id"] == msg.tool_call_id:
                                if call["name"] == "web_search":
                                    web_search_already_used = True
                                break

                    if web_search_already_used:
                        break

            if web_search_already_used:
                break

        # -----------------------------------------------------
        # Remove repeated web_search calls.
        # -----------------------------------------------------

        allowed_calls = []

        for call in tool_calls:

            tool_name = call["name"]

            if tool_name == "web_search" and web_search_already_used:

                # Instead of executing another web search,
                # return a ToolMessage telling Gemini to use
                # the existing search results.
                return {
                    "messages": [
                        ToolMessage(
                            content=(
                                "WEB_SEARCH_BLOCKED: A web_search call was "
                                "already executed for this user request. "
                                "Do not search again. Use the previous search "
                                "results and provide the final answer now."
                            ),
                            tool_call_id=call["id"],
                        )
                    ]
                }

            allowed_calls.append(call)

        # -----------------------------------------------------
        # Execute allowed tools normally.
        # -----------------------------------------------------

        if not allowed_calls:
            return {"messages": []}

        filtered_message = AIMessage(
            content=last_message.content,
            tool_calls=allowed_calls,
            id=last_message.id,
        )

        filtered_state = {
            "messages": messages[:-1] + [filtered_message]
        }

        return await normal_tool_node.ainvoke(filtered_state)

    # ---------------------------------------------------------
    # Build graph
    # ---------------------------------------------------------

    graph = StateGraph(AgentState)

    graph.add_node("agent", agent_node)
    graph.add_node("tools", guarded_tool_node)

    graph.add_edge(START, "agent")

    graph.add_conditional_edges(
        "agent",
        tools_condition,
        {
            "tools": "tools",
            END: END,
        },
    )

    graph.add_edge("tools", "agent")

    return graph.compile(
        checkpointer=MemorySaver()
    )


class AgentRunner:

    def __init__(self, tools):
        self.graph = build_graph(tools)

    async def run(
        self,
        user_text: str,
        thread_id: str
    ) -> AgentResult:

        config = {
            "configurable": {
                "thread_id": thread_id
            },
            "recursion_limit": settings.MAX_AGENT_STEPS,
        }

        steps: dict[str, dict] = {}
        answer = ""

        try:

            async for update in self.graph.astream(
                {
                    "messages": [
                        HumanMessage(content=user_text)
                    ]
                },
                config,
                stream_mode="updates",
            ):

                for node, payload in update.items():

                    for msg in payload.get("messages", []):

                        # ---------------------------------------------
                        # AI message
                        # ---------------------------------------------

                        if isinstance(msg, AIMessage):

                            for call in msg.tool_calls:

                                steps[call["id"]] = {
                                    "tool": call["name"],
                                    "args": call["args"],
                                    "result": None,
                                }

                            if not msg.tool_calls:
                                answer = _text(msg.content)

                        # ---------------------------------------------
                        # Tool result
                        # ---------------------------------------------

                        elif isinstance(msg, ToolMessage):

                            if msg.tool_call_id in steps:

                                steps[msg.tool_call_id]["result"] = _text(
                                    msg.content
                                )

            return AgentResult(
                answer or "(The model returned an empty response.)",
                list(steps.values()),
            )

        except Exception as exc:

            return AgentResult(
                "",
                list(steps.values()),
                self._friendly_error(exc),
            )

    @staticmethod
    def _friendly_error(exc: Exception) -> str:

        text = str(exc)
        low = text.lower()

        if (
            "api key" in low
            or "api_key" in low
            or "permission" in low
            or "401" in low
        ):
            return (
                "The Gemini API key looks invalid. "
                "Check GOOGLE_API_KEY in your .env."
            )

        if (
            "quota" in low
            or "429" in low
            or "resource_exhausted" in low
        ):
            return (
                "Gemini rate limit/quota reached. "
                "Wait a moment and try again."
            )

        if "recursion" in low:
            return (
                "The agent took too many steps. "
                "Try a simpler or more specific request."
            )

        if (
            "connection" in low
            or "timeout" in low
            or "unavailable" in low
        ):
            return (
                "Network problem while contacting a service. "
                "Check your connection."
            )

        return (
            f"Unexpected error: "
            f"{type(exc).__name__}: {text[:300]}"
        )
