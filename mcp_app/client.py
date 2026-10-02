"""MCP client layer: connects to every configured MCP server and discovers tools.

The agent never imports tool functions. It only receives whatever tools the
MCP servers advertise at runtime - that is what makes tool use dynamic.
"""
from dataclasses import dataclass, field

from langchain_core.tools import BaseTool
from langchain_mcp_adapters.client import MultiServerMCPClient


@dataclass
class ToolLoadResult:
    tools: list[BaseTool] = field(default_factory=list)
    by_server: dict[str, list[BaseTool]] = field(default_factory=dict)
    errors: dict[str, str] = field(default_factory=dict)  # server name -> error


class MCPToolManager:
    def __init__(self, servers: dict):
        self.servers = servers
        self.client = MultiServerMCPClient(servers)

    async def load_tools(self) -> ToolLoadResult:
        """Ask each MCP server for its tools. One broken server does not
        stop the others from loading."""
        result = ToolLoadResult()
        for name in self.servers:
            try:
                server_tools = await self.client.get_tools(server_name=name)
                result.by_server[name] = server_tools
                result.tools.extend(server_tools)
            except BaseException as exc:  # includes ExceptionGroup from anyio
                if isinstance(exc, (KeyboardInterrupt, SystemExit)):
                    raise
                result.errors[name] = f"{type(exc).__name__}: {exc}"
        return result
