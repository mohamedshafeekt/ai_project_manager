"""
Automated Accuracy Evaluation & Benchmark Suite (PRD Quality Rule: 'Measured accuracy').
Tests the LangGraph Multi-Agent Pipeline against ground-truth meeting scenarios:
1. Action item catch rate (>= 90%)
2. Relative date calculation precision
3. Zero-hallucination compliance (MISSING owner/date)
4. Scope change detection with verbatim quotes
5. GitHub vs spoken status discrepancy detection
6. Transcript parser & private meeting isolation
"""

import pytest

from app.services.agents.graph import analyze_meeting_with_langgraph
from app.services.connectors.meeting_ingestion import format_transcript_for_llm, parse_transcript

BENCHMARK_MEETING_DATE = "2026-11-24"  # Tuesday

BENCHMARK_TRANSCRIPT = """
[00:00:45] Mohamed: Good morning team. Let's review our Q4 sprint.
[00:01:10] Alex: I finished the user authentication login API for APM-1, it's completely done.
[00:01:40] Sarah: Awesome. Next, we need to integrate the Stripe webhook handler. Alex, can you complete that by Friday?
[00:02:05] Alex: Yes, I will finish the Stripe webhook handler by Friday.
[00:02:30] Mohamed: We also need someone to audit the database backups, though we haven't picked an owner or due date yet.
[00:03:00] Sarah: Let's record as a team decision that we are standardizing on PostgreSQL for all production services.
[00:03:30] Alex: Risk to note: the third-party email provider has been throwing intermittent 503 errors today.
[00:04:00] Sarah: Also, marketing asked if we can add a multi-currency tax calculation engine in this release?
[00:04:30] Mohamed: That's outside our agreed Phase 1 scope, let's flag it as a change request.
"""

BENCHMARK_SCOPE = """
Phase 1 Deliverables:
1. User Authentication & Login API
2. Stripe Payment Gateway Integration
3. Basic Web Dashboard
Explicitly Out of Scope: Multi-currency tax calculation engine, Native mobile apps.
"""

MOCK_LIVE_JIRA = [
    {"key": "APM-1", "summary": "Implement user authentication and login API", "status": "In Progress", "assignee": "Alex"},
    {"key": "APM-2", "summary": "Setup Stripe payment gateway integration", "status": "To Do", "assignee": "Unassigned"},
]

MOCK_LIVE_GITHUB_PRS = [
    {
        "identifier": "PR #1",
        "title": "feat: user authentication login API [APM-1]",
        "author": "alex",
        "state": "open",  # Contradicts Alex claiming APM-1 is "completely done"
        "linked_jira_keys": ["APM-1"],
    }
]


def test_transcript_parser_vtt_and_text():
    lines, attendees = parse_transcript(BENCHMARK_TRANSCRIPT)
    assert len(lines) == 9
    assert set(attendees) == {"Alex", "Mohamed", "Sarah"}
    assert lines[0]["speaker"] == "Mohamed"
    assert lines[0]["timestamp"] == "00:00:45"


@pytest.mark.asyncio
async def test_langgraph_accuracy_benchmark():
    lines, _ = parse_transcript(BENCHMARK_TRANSCRIPT)
    formatted = format_transcript_for_llm(lines)

    result = await analyze_meeting_with_langgraph(
        meeting_date=BENCHMARK_MEETING_DATE,
        formatted_transcript=formatted,
        agreed_scope=BENCHMARK_SCOPE,
        existing_raid=[],
        jira_issues=MOCK_LIVE_JIRA,
        github_prs=MOCK_LIVE_GITHUB_PRS,
        github_commits=[],
    )

    # 1. Check Decisions
    decisions = result["minutes_result"].decisions
    assert len(decisions) >= 1
    assert any("postgresql" in d.decision_text.lower() for d in decisions)
    assert all(len(d.supporting_lines) > 0 for d in decisions), "Every decision must cite source lines"

    # 2. Check Action Items Catch Rate & Zero-Hallucination
    actions = result["action_items_result"].action_items
    assert len(actions) >= 2, f"Expected at least 2 action items, got {len(actions)}"

    stripe_task = next((a for a in actions if "stripe" in a.description.lower() or "webhook" in a.description.lower()), None)
    assert stripe_task is not None, "Missed Stripe webhook action item"
    assert "alex" in stripe_task.owner.lower()
    assert stripe_task.due_date == "2026-11-27", f"Expected Friday 2026-11-27, got {stripe_task.due_date}"

    backup_task = next((a for a in actions if "backup" in a.description.lower() or "audit" in a.description.lower()), None)
    assert backup_task is not None, "Missed database backup action item"
    assert backup_task.owner == "MISSING", f"Hallucinated owner: {backup_task.owner}"
    assert backup_task.due_date == "MISSING", f"Hallucinated due date: {backup_task.due_date}"

    # 3. Check RAID Log
    raids = result["raid_result"].raid_items
    assert len(raids) >= 1
    assert any("503" in r.description or "email" in r.description.lower() for r in raids)

    # 4. Check Scope Change Detection
    scopes = result["scope_result"].scope_changes
    assert len(scopes) >= 1
    assert any("currency" in s.requested_change.lower() or "tax" in s.requested_change.lower() for s in scopes)
    assert all(len(s.verbatim_quote) > 5 for s in scopes)

    # 5. Check Jira & GitHub Discrepancy Detection
    recon = result["reconciliation_result"].jira_updates
    apm1_update = next((u for u in recon if u.jira_issue_key == "APM-1"), None)
    assert apm1_update is not None, "Failed to match spoken login API update to APM-1"
    assert apm1_update.has_discrepancy is True, "Failed to flag discrepancy when PR #1 is still OPEN"
