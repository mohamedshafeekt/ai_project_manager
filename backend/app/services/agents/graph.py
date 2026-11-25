"""
LangGraph Multi-Agent Orchestrator for Meeting Analysis.
Follows official LangGraph StateGraph patterns with parallel specialist agent fan-out,
strict Pydantic structured outputs, LangSmith tracing, and zero-hallucination prompts.
"""

import operator
from typing import Annotated, Any, TypedDict

from langgraph.graph import END, START, StateGraph
from langsmith import traceable

from app.schemas.extraction import (
    ActionItemsExtractionResult,
    MinutesExtractionResult,
    RaidExtractionResult,
    ReconciliationResult,
    ScopeChangeExtractionResult,
)
from app.services.llm.client import llm_service


# =====================================================================
# 1. LangGraph Shared State Definition
# =====================================================================
class MeetingAnalysisState(TypedDict):
    # Inputs
    meeting_date: str            # ISO date e.g. "2026-11-24"
    formatted_transcript: str    # Numbered lines: "Line 1: [00:01] Alice: ..."
    agreed_scope: str            # Project baseline scope
    existing_raid: list[dict[str, Any]]
    jira_issues: list[dict[str, Any]]
    github_prs: list[dict[str, Any]]
    github_commits: list[dict[str, Any]]

    # Specialist Agent Outputs
    minutes_result: MinutesExtractionResult | None
    action_items_result: ActionItemsExtractionResult | None
    raid_result: RaidExtractionResult | None
    scope_result: ScopeChangeExtractionResult | None
    reconciliation_result: ReconciliationResult | None

    # Accumulated Metrics (parallel-safe via operator.add)
    total_tokens: Annotated[int, operator.add]
    total_cost_usd: Annotated[float, operator.add]

    # Scatter-Gather Fan-In Synthesis
    cross_agent_notes: list[str]
    synthesis_summary: str | None


# =====================================================================
# 2. Specialist Agent Nodes
# =====================================================================
@traceable(name="Agent: Minutes & Decisions")
async def minutes_node(state: MeetingAnalysisState) -> dict:
    system_prompt = (
        "You are an expert Project Management Minutes Agent.\n"
        "Read the numbered meeting transcript and produce:\n"
        "1. A crisp 3-5 sentence executive summary.\n"
        "2. A list of concrete group decisions agreed upon.\n"
        "CRITICAL RULES:\n"
        "- Every decision MUST cite exact 1-based line numbers from the transcript in supporting_lines.\n"
        "- If no clear decisions were made, return an empty list. NEVER invent decisions."
    )
    user_prompt = f"Meeting Date: {state['meeting_date']}\n\nTranscript:\n{state['formatted_transcript']}"
    res, tokens, cost = await llm_service.extract_structured(
        system_prompt, user_prompt, MinutesExtractionResult
    )
    return {"minutes_result": res, "total_tokens": tokens, "total_cost_usd": cost}


@traceable(name="Agent: Action Items")
async def action_items_node(state: MeetingAnalysisState) -> dict:
    from datetime import datetime
    try:
        dt = datetime.strptime(state['meeting_date'][:10], "%Y-%m-%d")
        date_with_day = dt.strftime("%A, %Y-%m-%d")
    except Exception:
        date_with_day = state['meeting_date']

    system_prompt = (
        "You are an expert Action Item Extraction Agent.\n"
        f"Today's meeting date is {date_with_day}.\n"
        "Extract every action item committed to in the transcript.\n"
        "CRITICAL RULES (Zero Hallucination):\n"
        "- Convert relative dates (e.g., 'by Friday', 'next Tuesday', 'tomorrow') into exact YYYY-MM-DD dates using the meeting date and day of week.\n"
        "- If the owner was NOT explicitly named in the transcript, set owner to 'MISSING'. NEVER guess.\n"
        "- If the due date was NOT explicitly mentioned, set due_date to 'MISSING'. NEVER guess.\n"
        "- Every action item MUST include exact supporting_lines (1-based line numbers)."
    )
    user_prompt = f"Transcript:\n{state['formatted_transcript']}"
    res, tokens, cost = await llm_service.extract_structured(
        system_prompt, user_prompt, ActionItemsExtractionResult
    )
    return {"action_items_result": res, "total_tokens": tokens, "total_cost_usd": cost}


@traceable(name="Agent: RAID Log Manager")
async def raid_node(state: MeetingAnalysisState) -> dict:
    system_prompt = (
        "You are an expert RAID Log (Risks, Assumptions, Issues, Dependencies) Agent.\n"
        "Analyze the transcript and identify:\n"
        "- Risks (things that might go wrong)\n"
        "- Issues (things already going wrong / blockers)\n"
        "- Assumptions (beliefs taken for granted without proof)\n"
        "- Dependencies (work blocked by or relying on another team/vendor/system)\n"
        "Compare against existing RAID items provided below. If a statement updates an existing entry, "
        "set action_type='update' and provide its existing_raid_id. Otherwise set action_type='new'.\n"
        "CRITICAL: Cite exact supporting_lines. Set owner to 'MISSING' if not explicitly stated."
    )
    existing_str = "\n".join(
        [f"- ID: {r['id']} | [{r['type'].upper()}] {r['description']} (Status: {r['status']})" for r in state["existing_raid"]]
    ) or "None logged yet."

    user_prompt = (
        f"Existing RAID Log:\n{existing_str}\n\n"
        f"Transcript:\n{state['formatted_transcript']}"
    )
    res, tokens, cost = await llm_service.extract_structured(
        system_prompt, user_prompt, RaidExtractionResult
    )
    return {"raid_result": res, "total_tokens": tokens, "total_cost_usd": cost}


@traceable(name="Agent: Scope Creep Detector")
async def scope_node(state: MeetingAnalysisState) -> dict:
    system_prompt = (
        "You are a strict Scope Change Detection Agent.\n"
        "Compare the meeting discussion against the project's Agreed Scope Baseline.\n"
        "Flag ANY requested feature, integration, or deliverable that is NOT covered by the agreed scope "
        "(or is explicitly listed as Out of Scope).\n"
        "CRITICAL RULES:\n"
        "- Include the exact verbatim_quote from the speaker.\n"
        "- Include exact supporting_lines (1-based line numbers).\n"
        "- If nothing out of scope was requested, return an empty list."
    )
    user_prompt = (
        f"Agreed Scope Baseline:\n{state['agreed_scope']}\n\n"
        f"Transcript:\n{state['formatted_transcript']}"
    )
    res, tokens, cost = await llm_service.extract_structured(
        system_prompt, user_prompt, ScopeChangeExtractionResult
    )
    return {"scope_result": res, "total_tokens": tokens, "total_cost_usd": cost}


@traceable(name="Agent: Jira & GitHub Reconciliation")
async def reconciliation_node(state: MeetingAnalysisState) -> dict:
    system_prompt = (
        "You are a Technical Work Reconciliation Agent.\n"
        "Cross-reference what team members claimed in the meeting against:\n"
        "1. Live Jira Issues (keys, summaries, current statuses)\n"
        "2. Live GitHub Pull Requests and Commits (PR state: open vs merged)\n\n"
        "TASKS:\n"
        "- When a speaker mentions progress on a task (e.g. 'the login API is done'), match it to the right Jira issue key.\n"
        "- Propose a status update (e.g., 'Done', 'In Progress') and a concise comment.\n"
        "- CHECK GITHUB REALITY: If a speaker claims work is 'done' or 'finished', verify if its linked GitHub PR is actually MERGED. "
        "If the PR is still OPEN or missing, set has_discrepancy=True and explain clearly in discrepancy_note!\n"
        "- Assign a realistic confidence_score (lower it if the match is uncertain or if there is a discrepancy).\n"
        "- Cite exact supporting_lines."
    )
    jira_str = "\n".join(
        [f"- [{i['key']}] {i['summary']} (Status: {i['status']}, Assignee: {i['assignee']})" for i in state["jira_issues"]]
    ) or "No Jira issues found."

    pr_str = "\n".join(
        [f"- {p['identifier']}: {p['title']} | State: {p['state'].upper()} | Linked Keys: {p['linked_jira_keys']} | Author: {p['author']}" for p in state["github_prs"]]
    ) or "No recent PRs."

    commit_str = "\n".join(
        [f"- {c['identifier']}: {c['title']} by {c['author']}" for c in state["github_commits"]]
    ) or "No recent commits."

    user_prompt = (
        f"Live Jira Issues:\n{jira_str}\n\n"
        f"Live GitHub Pull Requests:\n{pr_str}\n\n"
        f"Recent GitHub Commits:\n{commit_str}\n\n"
        f"Transcript:\n{state['formatted_transcript']}"
    )
    res, tokens, cost = await llm_service.extract_structured(
        system_prompt, user_prompt, ReconciliationResult
    )
    return {"reconciliation_result": res, "total_tokens": tokens, "total_cost_usd": cost}


@traceable(name="Agent: Scatter-Gather Synthesizer")
async def synthesizer_node(state: MeetingAnalysisState) -> dict:
    """
    Fan-in aggregator node that cross-checks all 5 parallel specialist outputs
    for discrepancies, missing fields, and overlapping scope/action items.
    """
    notes: list[str] = []

    action_res = state["action_items_result"]
    raid_res = state["raid_result"]
    scope_res = state["scope_result"]
    recon_res = state["reconciliation_result"]
    minutes_res = state["minutes_result"]

    actions = action_res.action_items if action_res else []
    raids = raid_res.raid_items if raid_res else []
    scopes = scope_res.scope_changes if scope_res else []
    updates = recon_res.jira_updates if recon_res else []
    decisions = minutes_res.decisions if minutes_res else []

    missing_owners = sum(1 for a in actions if a.owner == "MISSING")
    missing_dates = sum(1 for a in actions if a.due_date == "MISSING")
    if missing_owners or missing_dates:
        notes.append(
            f"Action Items needing PM fill-in: {missing_owners} missing owner(s), {missing_dates} missing due date(s)."
        )

    for u in updates:
        if u.has_discrepancy:
            notes.append(f"GitHub/Meeting discrepancy on {u.jira_issue_key}: {u.discrepancy_note}")

    scope_lines = {ln for s in scopes for ln in s.supporting_lines}
    for a in actions:
        if scope_lines.intersection(a.supporting_lines):
            notes.append(
                f"Overlap: Action '{a.description[:50]}...' shares transcript lines with a Scope Change Request."
            )

    summary = (
        f"Synthesized {len(decisions)} decision(s), {len(actions)} action item(s), "
        f"{len(raids)} RAID entry/entries, {len(scopes)} scope change(s), and "
        f"{len(updates)} Jira update(s)."
    )
    return {"cross_agent_notes": notes, "synthesis_summary": summary}


# =====================================================================
# 3. Build & Compile the LangGraph Workflow
# =====================================================================
def build_meeting_graph():
    workflow = StateGraph(MeetingAnalysisState)

    # Add 5 specialist nodes + 1 fan-in synthesizer node
    workflow.add_node("minutes_agent", minutes_node)
    workflow.add_node("action_items_agent", action_items_node)
    workflow.add_node("raid_agent", raid_node)
    workflow.add_node("scope_agent", scope_node)
    workflow.add_node("reconciliation_agent", reconciliation_node)
    workflow.add_node("synthesizer_agent", synthesizer_node)

    # Fan-out from START in parallel for maximum speed (< 5 min SLA)
    parallel_agents = [
        "minutes_agent",
        "action_items_agent",
        "raid_agent",
        "scope_agent",
        "reconciliation_agent",
    ]
    for agent_name in parallel_agents:
        workflow.add_edge(START, agent_name)

    # Fan-in all 5 specialist agents into synthesizer_agent, then END
    for agent_name in parallel_agents:
        workflow.add_edge(agent_name, "synthesizer_agent")
    workflow.add_edge("synthesizer_agent", END)

    return workflow.compile()


meeting_analysis_graph = build_meeting_graph()


@traceable(name="Run Full Meeting Analysis Pipeline")
async def analyze_meeting_with_langgraph(
    meeting_date: str,
    formatted_transcript: str,
    agreed_scope: str,
    existing_raid: list[dict[str, Any]],
    jira_issues: list[dict[str, Any]],
    github_prs: list[dict[str, Any]],
    github_commits: list[dict[str, Any]],
) -> MeetingAnalysisState:
    """Executes the compiled LangGraph workflow and returns the complete extracted state."""
    initial_state: MeetingAnalysisState = {
        "meeting_date": meeting_date,
        "formatted_transcript": formatted_transcript,
        "agreed_scope": agreed_scope,
        "existing_raid": existing_raid,
        "jira_issues": jira_issues,
        "github_prs": github_prs,
        "github_commits": github_commits,
        "minutes_result": None,
        "action_items_result": None,
        "raid_result": None,
        "scope_result": None,
        "reconciliation_result": None,
        "total_tokens": 0,
        "total_cost_usd": 0.0,
        "cross_agent_notes": [],
        "synthesis_summary": None,
    }
    final_state = await meeting_analysis_graph.ainvoke(initial_state)
    return final_state
