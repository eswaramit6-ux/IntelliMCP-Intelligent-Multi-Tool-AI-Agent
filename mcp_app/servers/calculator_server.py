"""MCP server: calculator."""
import sys
from pathlib import Path

# Let this script import project packages (config/, tools/) when run as a subprocess.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from mcp.server.fastmcp import FastMCP

from tools.safe_math import safe_eval

server = FastMCP("calculator")


@server.tool()
def calculate(expression: str) -> str:
    """Evaluate a math expression, e.g. '25 * 48', 'sqrt(144) + 2^3', '(10+5)/3'.
    Supports + - * / // % ** ^, parentheses, sqrt, sin, cos, tan, log, exp, pi, e.
    Use this for ANY arithmetic instead of calculating mentally."""
    try:
        result = safe_eval(expression)
        return f"{expression} = {result}"
    except ZeroDivisionError:
        return "Error: division by zero."
    except Exception as exc:
        return f"Error: could not evaluate '{expression}' ({exc})."


if __name__ == "__main__":
    server.run(transport="stdio")
