# 🤖 Intelligent AI Agent with LangGraph and MCP

A Streamlit chat app where a **LangGraph ReAct agent** (powered by Gemini) understands a
natural-language request, picks the right tool by itself, runs it through **MCP**
(Model Context Protocol), and answers in plain language.

## Folder structure

```
langgraph-mcp-agent/
├── app.py                      # Streamlit chat UI
├── agents/
│   └── agent.py                # LangGraph StateGraph (ReAct loop) + memory
├── mcp_app/                    # (named mcp_app so it doesn't shadow the real `mcp` package)
│   ├── client.py               # MCP client: connects to servers, discovers tools
│   └── servers/
│       ├── calculator_server.py    # calculate
│       ├── search_server.py        # web_search (DuckDuckGo, no key)
│       ├── weather_server.py       # get_weather (Open-Meteo, no key)
│       ├── datetime_server.py      # get_current_time, convert_time
│       └── database_server.py      # get_database_schema, query_database (SQLite)
├── tools/                      # helpers used by servers (safe math, sample DB)
├── config/settings.py          # env vars + MCP server registry
├── data/                       # sample SQLite DB is auto-created here
├── requirements.txt
├── .env.example
└── README.md
```

## Installation

Requires Python 3.10+.

```bash
cd langgraph-mcp-agent
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## `.env` configuration

1. Get a free Gemini API key: https://aistudio.google.com/apikey
2. Copy the template and edit it:
   ```bash
   cp .env.example .env             # Windows: copy .env.example .env
   ```
3. Set `GOOGLE_API_KEY=your_real_key` in `.env`. (Optional: `GEMINI_MODEL`, `LLM_TEMPERATURE`.)

The key is only read from the environment; it is never in source code. `.env` is git-ignored.

## Run

```bash
streamlit run app.py
```
Open http://localhost:8501. The sidebar shows the MCP servers/tools discovered at startup.

## Example queries

| Tool | Try asking |
|---|---|
| Calculator | `What is 25 × 48?` · `What is sqrt(144) + 2^10?` |
| Weather | `What's the weather in Visakhapatnam?` · `Will it rain in London in the next 3 days?` |
| Date/time | `What time is it in Tokyo?` · `Convert 15:00 London time to Kolkata time` |
| Search | `Search the web for the latest news on LangGraph` |
| Database | `List all employees in Sales and their salaries` · `Which product has the lowest stock?` |
| No tool | `Explain what MCP is in two sentences.` |
| Memory | Ask `What is 25 × 48?` then `Now divide that by 4` |

Each tool call appears in an expandable "🔧 Tool used" panel showing input and result.

## Architecture and workflow

```
User ─► Streamlit UI (app.py)
          │  asyncio.run(runner.run(...))
          ▼
     LangGraph agent (agents/agent.py)
       ┌──────────┐  tool calls?  ┌───────────┐
       │  agent   │──────yes─────►│   tools   │──┐
       │ (Gemini) │◄──────────────│ (ToolNode)│  │ loop until
       └────┬─────┘  results      └─────┬─────┘  │ no more tool calls
            │ no                        │ ◄──────┘
            ▼                           ▼
      final answer                MCP client (mcp_app/client.py)
                                        │ stdio
                      ┌────────┬────────┼─────────┬──────────┐
                      ▼        ▼        ▼         ▼          ▼
                 calculator  search  weather  datetime   database   (MCP servers)
```

1. **Discovery (startup):** `MCPToolManager` launches every server in `config/settings.py`
   (`MCP_SERVERS`) over stdio and asks each "what tools do you have?" (MCP `tools/list`).
   They are converted to LangChain tools. The agent has **no hardcoded tools**.
2. **Reasoning:** the `agent` node sends the conversation plus tool descriptions to Gemini.
   The LLM decides: answer directly, or request a tool call with arguments.
3. **Acting:** if a tool call is requested, LangGraph routes to the `tools` node, which calls
   the MCP server (`tools/call`) and appends the result to the state.
4. **Loop:** control returns to `agent`, which may call more tools or write the final answer.
   A step limit (`MAX_AGENT_STEPS`) prevents infinite loops.
5. **Memory:** LangGraph's `MemorySaver` checkpointer stores state per `thread_id`
   (one per browser session). "Clear chat" creates a new thread.

## Adding your own tool

Create `mcp_app/servers/my_server.py` using `FastMCP` and `@server.tool()` (copy any existing
server), then add one line to `MCP_SERVERS` in `config/settings.py`. Click **Reload tools**
in the sidebar. The agent will use it with no other code changes. The tool's docstring is what
the LLM reads to decide when to use it, so write it clearly.

## Error handling

| Problem | Behaviour |
|---|---|
| Missing/invalid API key | Clear message in the UI, no crash |
| An MCP server fails to start | Marked 🔴 in sidebar; other servers still work |
| Tool errors (bad math, bad SQL, unknown city, network) | Returned as text to the LLM, which explains it |
| Gemini quota / network issues | Friendly error message in the chat |

## Troubleshooting

- **`GOOGLE_API_KEY is missing`**: `.env` must be in the project root; restart Streamlit.
- **Model not found**: change `GEMINI_MODEL` in `.env` (e.g. `gemini-2.0-flash`).
- **Weather/search fail**: they need internet access (no API keys required).
- **Windows time zones**: `tzdata` is in requirements; reinstall if needed.

## Security notes

The calculator uses an AST whitelist (no `eval`). The database tool only allows a single
`SELECT` on a read-only connection.
