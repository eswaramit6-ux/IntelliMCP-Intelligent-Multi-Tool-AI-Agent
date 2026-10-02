"""Central configuration: environment variables and the MCP server registry."""
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parents[1]
load_dotenv(ROOT_DIR / ".env")  # reads GOOGLE_API_KEY etc. from .env

# ---- LLM settings (secrets come ONLY from the environment) ----
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
LLM_TEMPERATURE = float(os.getenv("LLM_TEMPERATURE", "0.2"))

# ---- Agent settings ----
MAX_AGENT_STEPS = 12  # safety limit for the reason -> act loop

# ---- MCP server registry ----
# Each entry launches one MCP server as a subprocess (stdio transport).
# To add a new tool server: write a FastMCP script and add ONE entry here.
# The agent discovers its tools automatically - no agent code changes needed.
SERVERS_DIR = ROOT_DIR / "mcp_app" / "servers"


def _stdio_server(script_name: str) -> dict:
    return {
        "command": sys.executable,  # same Python interpreter as the app
        "args": [str(SERVERS_DIR / script_name)],
        "transport": "stdio",
    }


MCP_SERVERS = {
    "calculator": _stdio_server("calculator_server.py"),
    "search": _stdio_server("search_server.py"),
    "weather": _stdio_server("weather_server.py"),
    "datetime": _stdio_server("datetime_server.py"),
    "database": _stdio_server("database_server.py"),
}

DB_PATH = ROOT_DIR / "data" / "company.db"
