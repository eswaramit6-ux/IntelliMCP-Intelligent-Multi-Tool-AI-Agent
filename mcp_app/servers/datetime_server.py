"""MCP server: date and time."""
import sys
from pathlib import Path

# Let this script import project packages (config/, tools/) when run as a subprocess.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from mcp.server.fastmcp import FastMCP

from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

server = FastMCP("datetime")


@server.tool()
def get_current_time(timezone: str = "UTC") -> str:
    """Get the current date and time in an IANA timezone, e.g. 'Asia/Tokyo',
    'America/New_York', 'Europe/London', 'Asia/Kolkata'. Convert city names to
    the matching IANA timezone yourself (Tokyo -> Asia/Tokyo)."""
    try:
        now = datetime.now(ZoneInfo(timezone))
    except (ZoneInfoNotFoundError, ValueError):
        return f"Unknown timezone '{timezone}'. Use an IANA name like 'Asia/Tokyo'."
    return now.strftime(f"%A, %d %B %Y, %H:%M:%S ({timezone}, UTC%z)")


@server.tool()
def convert_time(time_24h: str, from_timezone: str, to_timezone: str) -> str:
    """Convert today's clock time (HH:MM, 24-hour) between two IANA timezones."""
    try:
        hour, minute = map(int, time_24h.split(":"))
        src = datetime.now(ZoneInfo(from_timezone)).replace(
            hour=hour, minute=minute, second=0, microsecond=0)
        dst = src.astimezone(ZoneInfo(to_timezone))
    except (ZoneInfoNotFoundError, ValueError):
        return "Invalid time or timezone. Use HH:MM and IANA names like 'Asia/Tokyo'."
    return f"{time_24h} in {from_timezone} is {dst.strftime('%H:%M on %d %B %Y')} in {to_timezone}."


if __name__ == "__main__":
    server.run(transport="stdio")
