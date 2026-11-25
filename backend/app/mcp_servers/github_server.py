"""
GitHub FastMCP Server
Exposes live GitHub PR, commit, and Jira-key linking tools over MCP.
Run standalone via stdio: python -m app.mcp_servers.github_server
"""

from typing import Any

from fastmcp import FastMCP

from app.services.connectors.github_connector import GitHubMCPConnector

mcp = FastMCP("github-mcp-server")


@mcp.tool()
async def github_get_pull_requests(
    repo: str | None = None,
    limit: int = 20,
) -> list[dict[str, Any]]:
    """Fetch recent GitHub Pull Requests with merge state and extracted Jira ticket keys."""
    connector = GitHubMCPConnector(repo_override=repo)
    return await connector.get_recent_pull_requests(limit=limit)


@mcp.tool()
async def github_get_commits(
    repo: str | None = None,
    limit: int = 15,
) -> list[dict[str, Any]]:
    """Fetch recent GitHub commits on the default branch with extracted Jira ticket keys."""
    connector = GitHubMCPConnector(repo_override=repo)
    return await connector.get_recent_commits(limit=limit)


if __name__ == "__main__":
    mcp.run()
