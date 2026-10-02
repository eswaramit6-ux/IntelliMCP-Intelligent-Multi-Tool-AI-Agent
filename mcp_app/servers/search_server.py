"""MCP server: web search (DuckDuckGo, no API key needed)."""
import sys
from pathlib import Path

# Let this script import project packages (config/, tools/) when run as a subprocess.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from mcp.server.fastmcp import FastMCP

server = FastMCP("search")


@server.tool()
def web_search(query: str, max_results: int = 5) -> str:
    """Search the web for current information, news, or facts the model may not
    know. Returns titles, snippets and URLs."""
    try:
        try:
            from ddgs import DDGS
        except ImportError:  # older package name
            from duckduckgo_search import DDGS
        results = list(DDGS().text(query, max_results=max(1, min(max_results, 10))))
    except Exception as exc:
        return f"Search failed: {exc}"
    if not results:
        return "No results found."
    return "\n\n".join(
        f"{i}. {r.get('title', '')}\n   {r.get('body', '')}\n   {r.get('href', '')}"
        for i, r in enumerate(results, 1))


if __name__ == "__main__":
    server.run(transport="stdio")
