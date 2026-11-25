"""
Jira Cloud FastMCP Server
Exposes live Jira Cloud REST API v3 tools over the Model Context Protocol (MCP).
Run standalone via stdio: python -m app.mcp_servers.jira_server
"""

from typing import Any

from fastmcp import FastMCP

from app.services.connectors.jira_connector import JiraMCPConnector

mcp = FastMCP("jira-mcp-server")
_connector = JiraMCPConnector()


@mcp.tool()
async def jira_get_issues(project_key: str, max_results: int = 50) -> list[dict[str, Any]]:
    """Fetch open and recent Jira issues for a project using POST /rest/api/3/search/jql."""
    return await _connector.get_project_issues(project_key=project_key, max_results=max_results)


@mcp.tool()
async def jira_create_issue(
    project_key: str,
    summary: str,
    description: str,
    issue_type: str = "Task",
    idempotency_key: str | None = None,
) -> dict[str, Any]:
    """Create a new Jira issue with idempotency label protection so retries never duplicate."""
    return await _connector.create_issue(
        project_key=project_key,
        summary=summary,
        description=description,
        issue_type=issue_type,
        idempotency_key=idempotency_key,
    )


@mcp.tool()
async def jira_update_status(issue_key: str, target_status: str) -> dict[str, Any]:
    """Transition an existing Jira issue to a new workflow status."""
    return await _connector.update_issue_status(issue_key=issue_key, target_status=target_status)


@mcp.tool()
async def jira_add_comment(issue_key: str, comment_text: str) -> dict[str, Any]:
    """Add an Atlassian Document Format (ADF) comment to an existing Jira issue."""
    return await _connector.add_comment(issue_key=issue_key, comment_text=comment_text)


if __name__ == "__main__":
    mcp.run()
