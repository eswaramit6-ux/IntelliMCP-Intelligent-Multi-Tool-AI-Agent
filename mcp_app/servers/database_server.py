"""MCP server: read-only lookup in a sample company SQLite database."""
import sys
from pathlib import Path

# Let this script import project packages (config/, tools/) when run as a subprocess.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from mcp.server.fastmcp import FastMCP

from config.settings import DB_PATH
from tools.sample_db import ensure_db, get_schema, run_select

ensure_db(DB_PATH)
server = FastMCP("database")


@server.tool()
def get_database_schema() -> str:
    """Show the tables and columns of the company database (employees, products,
    orders). Call this first if unsure about column names."""
    return get_schema(DB_PATH)


@server.tool()
def query_database(sql: str) -> str:
    """Run ONE read-only SQLite SELECT query on the company database and return
    the rows. Example: SELECT name, salary FROM employees WHERE department='Sales'"""
    try:
        return run_select(DB_PATH, sql)
    except Exception as exc:
        return f"Query error: {exc}"


if __name__ == "__main__":
    server.run(transport="stdio")
