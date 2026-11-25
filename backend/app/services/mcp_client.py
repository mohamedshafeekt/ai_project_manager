"""
Unified MCP Client for AI Project Manager.
Uses fastmcp.Client to communicate with our Jira, GitHub, and Teams FastMCP servers
over the Model Context Protocol (MCP), and exposes LangChain StructuredTools
for LangGraph agents.
"""

import json
from typing import Any

from fastmcp import Client
from langchain_core.tools import StructuredTool
from langsmith import traceable

from app.mcp_servers.github_server import mcp as github_mcp
from app.mcp_servers.jira_server import mcp as jira_mcp
from app.mcp_servers.teams_server import mcp as teams_mcp


class ProjectMCPClient:
    """
    MCP Client managing connections to Jira, GitHub, and Teams MCP servers.
    Each server can be an in-process FastMCP instance, a stdio script/command dict,
    or a remote Streamable-HTTP/SSE URL.
    """

    def __init__(self, server_overrides: dict[str, Any] | None = None):
        self.servers: dict[str, Any] = {
            "jira": jira_mcp,
            "github": github_mcp,
            "teams": teams_mcp,
        }
        if server_overrides:
            self.servers.update(server_overrides)

    @traceable(run_type="tool", name="MCP Client: Call Tool")
    async def call_tool(
        self,
        server_name: str,
        tool_name: str,
        arguments: dict[str, Any] | None = None,
    ) -> Any:
        """Invokes an MCP tool on the specified server using the MCP protocol."""
        if server_name not in self.servers:
            raise ValueError(f"Unknown MCP server '{server_name}'. Available: {list(self.servers.keys())}")

        target = self.servers[server_name]
        async with Client(target) as client:
            result = await client.call_tool(tool_name, arguments or {})
            if result.data is not None:
                return result.data
            if getattr(result, "structured_content", None) is not None:
                return result.structured_content
            if result.content:
                first = result.content[0]
                text = getattr(first, "text", None)
                if text:
                    try:
                        return json.loads(text)
                    except json.JSONDecodeError:
                        return text
            return None

    async def list_all_tools(self) -> dict[str, list[dict[str, str]]]:
        """Discovers all tools exposed by each registered MCP server."""
        catalog: dict[str, list[dict[str, str]]] = {}
        for name, target in self.servers.items():
            async with Client(target) as client:
                tools = await client.list_tools()
                catalog[name] = [
                    {
                        "name": t.name,
                        "description": t.description or "",
                    }
                    for t in tools
                ]
        return catalog

    async def get_langchain_tools(
        self, server_names: list[str] | None = None
    ) -> list[StructuredTool]:
        """
        Converts MCP tools from the requested servers into LangChain StructuredTool
        objects ready to be bound to LangGraph agents.
        """
        targets = server_names or list(self.servers.keys())
        lc_tools: list[StructuredTool] = []

        for srv in targets:
            target = self.servers[srv]
            async with Client(target) as client:
                mcp_tools = await client.list_tools()
                for t in mcp_tools:
                    tool_name = t.name
                    tool_desc = t.description or f"MCP tool {tool_name} on {srv}"

                    async def _invoke(_srv=srv, _tool=tool_name, **kwargs) -> Any:
                        return await self.call_tool(_srv, _tool, kwargs)

                    lc_tools.append(
                        StructuredTool.from_function(
                            coroutine=_invoke,
                            name=tool_name,
                            description=tool_desc,
                        )
                    )
        return lc_tools


mcp_client = ProjectMCPClient()
