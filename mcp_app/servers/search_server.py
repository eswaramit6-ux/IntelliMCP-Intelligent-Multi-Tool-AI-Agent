"""MCP server: web search (DuckDuckGo, no API key needed)."""

import sys
from pathlib import Path

# Let this script import project packages (config/, tools/) when run as a subprocess.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from mcp.server.fastmcp import FastMCP

server = FastMCP("search")


@server.tool()
def web_search(query: str, max_results: int = 5) -> str:
    """Search the web for current information, news, facts, rankings,
    people, teams, companies, or other information that may require
    up-to-date web results.

    Call this tool when web information is needed.
    After receiving results, use them to answer the user directly.
    Do not repeatedly search for the same request unless the search
    actually fails or returns no results.
    """

    try:
        try:
            from ddgs import DDGS
        except ImportError:
            from duckduckgo_search import DDGS

        max_results = max(1, min(max_results, 5))

        results = list(
            DDGS().text(
                query,
                max_results=max_results
            )
        )

    except Exception as exc:
        return f"SEARCH_ERROR: {type(exc).__name__}: {exc}"

    if not results:
        return (
            f"NO_RESULTS: No search results were found for "
            f"the query: {query}"
        )

    output = [
        f"SEARCH_RESULTS for: {query}",
        f"Number of results: {len(results)}",
        ""
    ]

    for i, result in enumerate(results, 1):

        title = result.get("title", "").strip()
        body = result.get("body", "").strip()
        href = result.get("href", "").strip()

        output.append(
            f"Result {i}:\n"
            f"Title: {title}\n"
            f"Summary: {body}\n"
            f"URL: {href}"
        )

    return "\n\n".join(output)


if __name__ == "__main__":
    server.run(transport="stdio")
