"""
Tests for FastMCP servers, ProjectMCPClient (MCP protocol + LangChain StructuredTool adapter),
and the LangGraph Scatter-Gather synthesizer fan-in node.
"""

import pytest

from app.schemas.extraction import (
    ActionItemsExtractionResult,
    ExtractedActionItem,
    ExtractedDecision,
    ExtractedJiraUpdate,
    ExtractedScopeChange,
    MinutesExtractionResult,
    RaidExtractionResult,
    ReconciliationResult,
    ScopeChangeExtractionResult,
)
from app.services.agents.graph import synthesizer_node
from app.services.mcp_client import mcp_client


@pytest.mark.asyncio
async def test_mcp_tool_discovery_and_teams_call():
    """Verifies real MCP JSON-RPC tool discovery across Jira, GitHub, and Teams FastMCP servers."""
    catalog = await mcp_client.list_all_tools()
    assert "jira" in catalog and "github" in catalog and "teams" in catalog

    jira_names = {t["name"] for t in catalog["jira"]}
    assert {"jira_get_issues", "jira_create_issue", "jira_update_status", "jira_add_comment"}.issubset(jira_names)

    github_names = {t["name"] for t in catalog["github"]}
    assert {"github_get_pull_requests", "github_get_commits"}.issubset(github_names)

    teams_names = {t["name"] for t in catalog["teams"]}
    assert {"teams_parse_transcript", "teams_send_alert"}.issubset(teams_names)

    parsed = await mcp_client.call_tool(
        "teams",
        "teams_parse_transcript",
        {"raw_transcript": "Alice: We shipped KAN-1.\nBob: Agreed."},
    )
    assert parsed["attendees"] == ["Alice", "Bob"]
    assert len(parsed["lines"]) == 2

    lc_tools = await mcp_client.get_langchain_tools()
    assert len(lc_tools) >= 8


@pytest.mark.asyncio
async def test_synthesizer_fan_in_node():
    """Verifies Scatter-Gather synthesizer cross-checks missing fields, discrepancies, and overlaps."""
    state = {
        "meeting_date": "2026-11-24",
        "formatted_transcript": "",
        "agreed_scope": "",
        "existing_raid": [],
        "jira_issues": [],
        "github_prs": [],
        "github_commits": [],
        "minutes_result": MinutesExtractionResult(
            summary="Reviewed sprint progress.",
            decisions=[ExtractedDecision(decision_text="Ship MVP Friday", supporting_lines=[1])],
        ),
        "action_items_result": ActionItemsExtractionResult(
            action_items=[
                ExtractedActionItem(
                    description="Add Stripe billing integration",
                    owner="MISSING",
                    due_date="MISSING",
                    supporting_lines=[5],
                    confidence_score=0.9,
                )
            ]
        ),
        "raid_result": RaidExtractionResult(raid_items=[]),
        "scope_result": ScopeChangeExtractionResult(
            scope_changes=[
                ExtractedScopeChange(
                    requested_change="Stripe billing integration",
                    verbatim_quote="Can we add Stripe billing?",
                    supporting_lines=[5],
                    impact_summary="Adds 1 week",
                    confidence_score=0.92,
                )
            ]
        ),
        "reconciliation_result": ReconciliationResult(
            jira_updates=[
                ExtractedJiraUpdate(
                    jira_issue_key="KAN-1",
                    proposed_status="Done",
                    comment_to_add="Done per meeting",
                    supporting_lines=[2],
                    confidence_score=0.5,
                    has_discrepancy=True,
                    discrepancy_note="PR #1 is still OPEN on GitHub.",
                )
            ]
        ),
        "total_tokens": 100,
        "total_cost_usd": 0.001,
        "cross_agent_notes": [],
        "synthesis_summary": None,
    }

    out = await synthesizer_node(state)
    assert "Synthesized 1 decision(s), 1 action item(s)" in out["synthesis_summary"]
    notes_joined = " ".join(out["cross_agent_notes"])
    assert "1 missing owner(s), 1 missing due date(s)" in notes_joined
    assert "GitHub/Meeting discrepancy on KAN-1" in notes_joined
    assert "Overlap:" in notes_joined
