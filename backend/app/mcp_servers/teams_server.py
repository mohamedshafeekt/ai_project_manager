"""
Microsoft Teams & Meeting Ingestion FastMCP Server
Exposes transcript parsing, speaker/timestamp normalization, and alert tools over MCP.
Run standalone via stdio: python -m app.mcp_servers.teams_server
"""

from typing import Any

from fastmcp import FastMCP

from app.services.connectors.meeting_ingestion import (
    format_transcript_for_llm,
    parse_transcript,
)

mcp = FastMCP("teams-meetings-mcp-server")


@mcp.tool()
def teams_parse_transcript(raw_transcript: str) -> dict[str, Any]:
    """Parse Teams VTT, JSON, or speaker-timestamped text into numbered lines, attendees, and LLM format."""
    parsed_lines, attendees = parse_transcript(raw_transcript)
    formatted_text = format_transcript_for_llm(parsed_lines)
    return {
        "lines": parsed_lines,
        "attendees": attendees,
        "formatted_text": formatted_text,
    }


@mcp.tool()
def teams_send_alert(recipient: str, message: str, channel: str = "teams-pm-alerts") -> dict[str, Any]:
    """Send an approved deadline or status notification to a Teams channel or member."""
    # In production, posts to Microsoft Teams Incoming Webhook / Graph API post-approval
    return {
        "status": "queued",
        "channel": channel,
        "recipient": recipient,
        "message": message,
    }


if __name__ == "__main__":
    mcp.run()
