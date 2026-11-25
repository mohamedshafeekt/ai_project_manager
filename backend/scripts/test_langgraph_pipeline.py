"""
End-to-end verification of:
1. Live Jira & GitHub MCP Connectors
2. LangGraph Parallel StateGraph Multi-Agent Pipeline
3. Structured Pydantic Output & LangSmith Tracing
"""

import asyncio

from app.config import settings
from app.services.agents.graph import analyze_meeting_with_langgraph
from app.services.connectors.github_connector import GitHubMCPConnector
from app.services.connectors.jira_connector import JiraMCPConnector
from app.services.connectors.meeting_ingestion import format_transcript_for_llm, parse_transcript

SAMPLE_TRANSCRIPT = """
[00:01:05] Mohamed: Welcome everyone to our Tuesday sprint sync. Let's review progress.
[00:01:30] Alex: The login API and README update for KAN-1 are completely done and tested.
[00:02:00] Mohamed: Great! Also, we need to finalize the Stripe webhook handler. Alex, can you finish that by Friday?
[00:02:20] Alex: Sure, I will get the Stripe webhook handler done by Friday.
[00:02:45] Sarah: We also decided as a team to use PostgreSQL on Neon for our production database instead of SQLite.
[00:03:15] Alex: One risk to flag: the external payment sandbox API has been timing out intermittently this morning.
[00:03:50] Sarah: By the way, a stakeholder asked if we can also build a native iOS mobile app in this release?
[00:04:15] Mohamed: Let's note that request, though it wasn't in our Phase 1 agreement. Also someone needs to update the deployment docs, though we don't have an owner or date for that yet.
"""

AGREED_SCOPE = """
Phase 1 Deliverables:
1. User Authentication & Login API
2. Stripe Payment Gateway Integration
3. User Profile API & Basic Web Dashboard
Explicitly Out of Scope: Native mobile applications (iOS/Android), Multi-currency tax engine.
"""


async def main():
    print("1. Fetching live Jira issues...")
    jira = JiraMCPConnector()
    jira_issues = await jira.get_project_issues(settings.JIRA_PROJECT_KEY)
    print(f"   Fetched {len(jira_issues)} Jira issues.")

    print("2. Fetching live GitHub PRs and commits...")
    gh = GitHubMCPConnector()
    prs = await gh.get_recent_pull_requests()
    commits = await gh.get_recent_commits()
    print(f"   Fetched {len(prs)} PRs and {len(commits)} commits.")

    print("3. Parsing transcript...")
    lines, attendees = parse_transcript(SAMPLE_TRANSCRIPT)
    formatted = format_transcript_for_llm(lines)
    print(f"   Parsed {len(lines)} lines. Attendees: {attendees}")

    print("4. Running LangGraph Multi-Agent Pipeline (5 parallel agents)...")
    result = await analyze_meeting_with_langgraph(
        meeting_date="2026-11-24",
        formatted_transcript=formatted,
        agreed_scope=AGREED_SCOPE,
        existing_raid=[],
        jira_issues=jira_issues,
        github_prs=prs,
        github_commits=commits,
    )

    print("\n" + "=" * 60)
    print("LANGGRAPH RESULTS:")
    print("=" * 60)
    print(f"Total Tokens: {result['total_tokens']} | Est. Cost: ${result['total_cost_usd']:.6f}\n")

    print("--- MINUTES & DECISIONS ---")
    print("Summary:", result["minutes_result"].summary)
    for d in result["minutes_result"].decisions:
        print(f"  * Decision: {d.decision_text} (Lines: {d.supporting_lines})")

    print("\n--- ACTION ITEMS ---")
    for a in result["action_items_result"].action_items:
        print(f"  * [{a.owner}] {a.description} | Due: {a.due_date} (Lines: {a.supporting_lines})")

    print("\n--- RAID LOG ---")
    for r in result["raid_result"].raid_items:
        print(f"  * [{r.raid_type.upper()} - {r.severity}] {r.description} | Owner: {r.owner} (Lines: {r.supporting_lines})")

    print("\n--- SCOPE CHANGES ---")
    for s in result["scope_result"].scope_changes:
        print(f"  * Change: {s.requested_change}\n    Quote: \"{s.verbatim_quote}\" (Lines: {s.supporting_lines})")

    print("\n--- JIRA & GITHUB RECONCILIATION ---")
    for j in result["reconciliation_result"].jira_updates:
        print(f"  * Issue {j.jira_issue_key} -> Proposed Status: {j.proposed_status} | Confidence: {j.confidence_score}")
        if j.has_discrepancy:
            print(f"    [!] DISCREPANCY: {j.discrepancy_note}")
        print(f"    Evidence: {j.github_evidence} (Lines: {j.supporting_lines})")


if __name__ == "__main__":
    asyncio.run(main())
