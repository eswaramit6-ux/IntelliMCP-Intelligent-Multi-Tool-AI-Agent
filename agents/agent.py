"""LangGraph ReAct agent.

Graph:   START -> agent --(tool calls?)--> tools -> agent -> ... -> END
  * agent : the LLM reasons and either answers or requests a tool call
  * tools : executes the requested MCP tool(s) and returns the results
Conversation memory is handled by LangGraph's MemorySaver checkpointer.
"""
from dataclasses import dataclass, field
from typing import Annotated, TypedDict

from langchain_core.messages import AIMessage, AnyMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode, tools_condition

from config import settings

SYSTEM_PROMPT = """You are a helpful AI assistant with access to external tools via MCP.

- Decide whether a tool is needed.
- Use tools for arithmetic, current weather, current time, live web information, and company database questions.
- Answer general knowledge or conversational questions directly WITHOUT tools.
- For web-search requests, call web_search to obtain relevant information.
- Normally make only ONE web_search call per user request.
- After receiving search results, use those results to formulate the answer directly.
- Do NOT repeatedly call web_search for the same or similar request.
- Do NOT call web_search again merely because the results are imperfect or because you want more results.
- Only retry web_search if the previous call returned SEARCH_ERROR or NO_RESULTS.
- If search results are available, answer using the available evidence.
- If the user's question is ambiguous, explain the ambiguity or ask a concise clarification when necessary.
- If a tool returns an error, explain it simply and try an alternative only when appropriate.
- Use earlier messages in the conversation to resolve follow-up questions.
- Be concise and friendly."""


class AgentConfigError(Exception):
    """Raised for setup problems such as a missing API key."""


class AgentState(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]


@dataclass
class AgentResult:
    answer: str
    steps: list[dict] = field(default_factory=list)  # tool calls made this turn
    error: str | None = None


def _text(content) -> str:
    """Gemini may return a string or a list of content blocks; normalise to text."""
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
        raise AgentConfigError("GOOGLE_API_KEY is missing. Add it to your .env file.")

    llm = ChatGoogleGenerativeAI(
        model=settings.GEMINI_MODEL,
        google_api_key=settings.GOOGLE_API_KEY,
        temperature=settings.LLM_TEMPERATURE,
    )
    llm_with_tools = llm.bind_tools(tools) if tools else llm

    async def agent_node(state: AgentState):
        messages = [SystemMessage(content=SYSTEM_PROMPT)] + state["messages"]
        return {"messages": [await llm_with_tools.ainvoke(messages)]}

    graph = StateGraph(AgentState)
    graph.add_node("agent", agent_node)
    graph.add_node("tools", ToolNode(tools, handle_tool_errors=True))
    graph.add_edge(START, "agent")
    graph.add_conditional_edges("agent", tools_condition, {"tools": "tools", END: END})
    graph.add_edge("tools", "agent")
    return graph.compile(checkpointer=MemorySaver())


class AgentRunner:
    def __init__(self, tools):
        self.graph = build_graph(tools)

    async def run(self, user_text: str, thread_id: str) -> AgentResult:
        config = {"configurable": {"thread_id": thread_id},
                  "recursion_limit": settings.MAX_AGENT_STEPS}
        steps: dict[str, dict] = {}
        answer = ""
        try:
            async for update in self.graph.astream(
                {"messages": [HumanMessage(content=user_text)]},
                config, stream_mode="updates",
            ):
                for node, payload in update.items():
                    for msg in payload.get("messages", []):
                        if isinstance(msg, AIMessage):
                            for call in msg.tool_calls:
                                steps[call["id"]] = {"tool": call["name"],
                                                     "args": call["args"], "result": None}
                            if not msg.tool_calls:
                                answer = _text(msg.content)
                        elif isinstance(msg, ToolMessage):
                            if msg.tool_call_id in steps:
                                steps[msg.tool_call_id]["result"] = _text(msg.content)
        except Exception as exc:
            return AgentResult("", list(steps.values()), self._friendly_error(exc))
        return AgentResult(answer or "(The model returned an empty response.)",
                           list(steps.values()))

    @staticmethod
    def _friendly_error(exc: Exception) -> str:
        text = str(exc)
        low = text.lower()
        if "api key" in low or "api_key" in low or "permission" in low or "401" in low:
            return "The Gemini API key looks invalid. Check GOOGLE_API_KEY in your .env."
        if "quota" in low or "429" in low or "resource_exhausted" in low:
            return "Gemini rate limit/quota reached. Wait a moment and try again."
        if "recursion" in low:
            return "The agent took too many steps. Try a simpler or more specific request."
        if "connection" in low or "timeout" in low or "unavailable" in low:
            return "Network problem while contacting a service. Check your connection."
        return f"Unexpected error: {type(exc).__name__}: {text[:300]}"
