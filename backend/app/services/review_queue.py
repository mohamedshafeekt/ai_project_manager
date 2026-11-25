"""
Review Queue & Human-in-the-Loop Approval Engine.
Ensures NOTHING touches Jira or official project logs without PM approval (PRD Principle 1).
Handles:
- Private meeting enforcement (never read or store private transcripts)
- Persisting LangGraph outputs as DraftUpdate items
- Approve / Edit & Approve / Reject / Batch Approve
- Idempotent Jira writes with safe retry on failure
- Complete AuditHistory logging
"""

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    ActionItem,
    AuditHistory,
    CodeActivityLink,
    Decision,
    DraftUpdate,
    Meeting,
    Project,
    RaidItem,
    ScopeChangeRequest,
    TranscriptLine,
)
from app.services.agents.graph import analyze_meeting_with_langgraph
from app.services.mcp_client import mcp_client


async def ingest_and_analyze_meeting(
    db: AsyncSession,
    project: Project,
    title: str,
    meeting_date: datetime,
    raw_transcript: str,
    is_private: bool = False,
) -> Meeting:
    """
    Ingests a meeting transcript.
    If is_private=True, strictly skips reading, storing transcript text, or calling AI.
    """
    if is_private:
        meeting = Meeting(
            project_id=project.id,
            title=title,
            meeting_date=meeting_date,
            attendees=[],
            is_private=True,
            raw_transcript="",  # Never stored
            status="private_skipped",
            token_count=0,
            cost_usd=0.0,
        )
        db.add(meeting)
        await db.commit()
        await db.refresh(meeting)
        return meeting

    # 1. Parse transcript into numbered lines via Teams MCP Server
    parsed_data = await mcp_client.call_tool(
        "teams", "teams_parse_transcript", {"raw_transcript": raw_transcript}
    )
    parsed_lines = parsed_data["lines"]
    attendees = parsed_data["attendees"]
    formatted_text = parsed_data["formatted_text"]

    meeting = Meeting(
        project_id=project.id,
        title=title,
        meeting_date=meeting_date,
        attendees=attendees,
        is_private=False,
        raw_transcript=raw_transcript,
        status="processing",
    )
    db.add(meeting)
    await db.flush()

    for line in parsed_lines:
        db.add(
            TranscriptLine(
                meeting_id=meeting.id,
                line_number=line["line_number"],
                speaker=line["speaker"],
                timestamp=line.get("timestamp", ""),
                text=line["text"],
            )
        )

    # 2. Fetch live context from Jira, GitHub, and existing RAID log via MCP Client
    try:
        jira_issues = await mcp_client.call_tool(
            "jira", "jira_get_issues", {"project_key": project.jira_project_key}
        )
    except Exception as e:
        print(f"[Warn] Could not fetch Jira issues via MCP: {e}")
        jira_issues = []

    try:
        github_prs = await mcp_client.call_tool(
            "github", "github_get_pull_requests", {"repo": project.github_repo}
        )
        github_commits = await mcp_client.call_tool(
            "github", "github_get_commits", {"repo": project.github_repo}
        )
    except Exception as e:
        print(f"[Warn] Could not fetch GitHub activity via MCP: {e}")
        github_prs = []
        github_commits = []

    # Refresh CodeActivityLink table for this project
    await _sync_code_activity_links(db, project, github_prs)

    raid_rows = (
        await db.execute(select(RaidItem).where(RaidItem.project_id == project.id))
    ).scalars().all()
    existing_raid = [
        {"id": r.id, "type": r.type, "description": r.description, "status": r.status}
        for r in raid_rows
    ]

    # 3. Execute LangGraph Multi-Agent Pipeline
    date_str = meeting_date.strftime("%Y-%m-%d")
    state = await analyze_meeting_with_langgraph(
        meeting_date=date_str,
        formatted_transcript=formatted_text,
        agreed_scope=project.agreed_scope,
        existing_raid=existing_raid,
        jira_issues=jira_issues,
        github_prs=github_prs,
        github_commits=github_commits,
    )

    # 4. Save all extracted items into DraftUpdate queue (waiting for PM approval)
    minutes_res = state.get("minutes_result")
    if minutes_res:
        for d in minutes_res.decisions:
            db.add(
                DraftUpdate(
                    project_id=project.id,
                    meeting_id=meeting.id,
                    category="decision",
                    title=f"Decision: {d.decision_text[:80]}",
                    proposed_payload={
                        "decision_text": d.decision_text,
                        "meeting_summary": minutes_res.summary,
                    },
                    supporting_lines=d.supporting_lines,
                    confidence_score=0.95,
                    status="waiting",
                )
            )

    action_res = state.get("action_items_result")
    if action_res:
        for a in action_res.action_items:
            db.add(
                DraftUpdate(
                    project_id=project.id,
                    meeting_id=meeting.id,
                    category="action_item",
                    title=f"Action: {a.description[:80]}",
                    proposed_payload={
                        "description": a.description,
                        "owner": a.owner,
                        "due_date": a.due_date,
                        "sync_to_jira": True,
                    },
                    supporting_lines=a.supporting_lines,
                    confidence_score=a.confidence_score,
                    status="waiting",
                )
            )

    raid_res = state.get("raid_result")
    if raid_res:
        for r in raid_res.raid_items:
            db.add(
                DraftUpdate(
                    project_id=project.id,
                    meeting_id=meeting.id,
                    category="raid_item",
                    title=f"{r.raid_type.upper()} ({r.severity}): {r.description[:70]}",
                    proposed_payload={
                        "action_type": r.action_type,
                        "existing_raid_id": r.existing_raid_id,
                        "type": r.raid_type,
                        "description": r.description,
                        "severity": r.severity,
                        "owner": r.owner,
                        "status": r.status,
                    },
                    supporting_lines=r.supporting_lines,
                    confidence_score=r.confidence_score,
                    status="waiting",
                )
            )

    scope_res = state.get("scope_result")
    if scope_res:
        for s in scope_res.scope_changes:
            db.add(
                DraftUpdate(
                    project_id=project.id,
                    meeting_id=meeting.id,
                    category="scope_change",
                    title=f"Scope Change: {s.requested_change[:75]}",
                    proposed_payload={
                        "requested_change": s.requested_change,
                        "verbatim_quote": s.verbatim_quote,
                        "impact_summary": s.impact_summary,
                    },
                    supporting_lines=s.supporting_lines,
                    confidence_score=s.confidence_score,
                    status="waiting",
                )
            )

    recon_res = state["reconciliation_result"]
    if recon_res:
        for j in recon_res.jira_updates:
            db.add(
                DraftUpdate(
                    project_id=project.id,
                    meeting_id=meeting.id,
                    category="jira_status_update",
                    title=f"Jira {j.jira_issue_key} -> {j.proposed_status or 'Comment'}",
                    proposed_payload={
                        "jira_issue_key": j.jira_issue_key,
                        "proposed_status": j.proposed_status,
                        "comment_to_add": j.comment_to_add,
                        "github_evidence": j.github_evidence,
                    },
                    supporting_lines=j.supporting_lines,
                    confidence_score=j.confidence_score,
                    discrepancy_note=j.discrepancy_note if j.has_discrepancy else None,
                    status="waiting",
                )
            )

            # Also flag discrepancy on CodeActivityLink if applicable
            if j.has_discrepancy:
                for pr in github_prs:
                    if j.jira_issue_key in pr.get("linked_jira_keys", []):
                        link = (
                            await db.execute(
                                select(CodeActivityLink).where(
                                    CodeActivityLink.project_id == project.id,
                                    CodeActivityLink.identifier == pr["identifier"],
                                )
                            )
                        ).scalar_one_or_none()
                        if link:
                            link.has_discrepancy = True
                            link.discrepancy_details = j.discrepancy_note

    meeting.token_count = state["total_tokens"]
    meeting.cost_usd = state["total_cost_usd"]
    meeting.status = "analyzed"

    await db.commit()
    await db.refresh(meeting)
    return meeting


async def _sync_code_activity_links(db: AsyncSession, project: Project, github_prs: list[dict[str, Any]]):
    """Upserts GitHub PR activity into CodeActivityLink."""
    for pr in github_prs:
        existing = (
            await db.execute(
                select(CodeActivityLink).where(
                    CodeActivityLink.project_id == project.id,
                    CodeActivityLink.identifier == pr["identifier"],
                )
            )
        ).scalar_one_or_none()
        linked_key = pr["linked_jira_keys"][0] if pr.get("linked_jira_keys") else None
        if existing:
            existing.state = pr["state"]
            existing.title = pr["title"]
            existing.jira_issue_key = linked_key
            existing.last_checked_at = datetime.now(UTC)
        else:
            db.add(
                CodeActivityLink(
                    project_id=project.id,
                    repo_name=project.github_repo,
                    activity_type="pull_request",
                    identifier=pr["identifier"],
                    title=pr["title"],
                    author=pr["author"],
                    state=pr["state"],
                    jira_issue_key=linked_key,
                    has_discrepancy=False,
                )
            )


async def approve_draft(
    db: AsyncSession,
    draft: DraftUpdate,
    project: Project,
    approver_name: str = "Project Manager",
    edited_payload: dict[str, Any] | None = None,
) -> AuditHistory:
    """
    Approves (or edits & approves) a DraftUpdate, commits it to local tables,
    dispatches live Jira updates with idempotency, and records AuditHistory.
    """
    original_payload = dict(draft.proposed_payload)
    final_payload = edited_payload if edited_payload is not None else original_payload
    action = "edited_and_approved" if edited_payload is not None else "approved"
    draft.status = "edited" if edited_payload is not None else "approved"
    draft.proposed_payload = final_payload

    jira_sync_status = "not_applicable"
    jira_sync_error = None
    jira_issue_key = None

    # Apply to domain tables + live Jira via MCP Client
    if draft.category == "decision":
        db.add(
            Decision(
                meeting_id=draft.meeting_id,
                decision_text=final_payload.get("decision_text", draft.title),
                supporting_lines=draft.supporting_lines,
            )
        )

    elif draft.category == "action_item":
        item = ActionItem(
            project_id=project.id,
            meeting_id=draft.meeting_id,
            description=final_payload.get("description", ""),
            owner=final_payload.get("owner", "MISSING"),
            due_date=final_payload.get("due_date", "MISSING"),
            status="todo",
            supporting_lines=draft.supporting_lines,
        )
        if final_payload.get("sync_to_jira", True):
            try:
                desc = (
                    f"{item.description}\n\n"
                    f"Owner: {item.owner}\nDue Date: {item.due_date}\n"
                    f"Approved by: {approver_name} (AI PM Agent)"
                )
                res = await mcp_client.call_tool(
                    "jira",
                    "jira_create_issue",
                    {
                        "project_key": project.jira_project_key,
                        "summary": item.description,
                        "description": desc,
                        "issue_type": "Task",
                        "idempotency_key": draft.id,
                    },
                )
                jira_issue_key = res.get("key")
                item.jira_issue_key = jira_issue_key
                jira_sync_status = "synced"
            except Exception as e:
                jira_sync_status = "failed"
                jira_sync_error = str(e)
        db.add(item)

    elif draft.category == "raid_item":
        existing_id = final_payload.get("existing_raid_id")
        if final_payload.get("action_type") == "update" and existing_id:
            existing_raid = (
                await db.execute(select(RaidItem).where(RaidItem.id == existing_id))
            ).scalar_one_or_none()
            if existing_raid:
                existing_raid.description = final_payload.get("description", existing_raid.description)
                existing_raid.severity = final_payload.get("severity", existing_raid.severity)
                existing_raid.status = final_payload.get("status", existing_raid.status)
                existing_raid.owner = final_payload.get("owner", existing_raid.owner)
            else:
                db.add(RaidItem(
                    project_id=project.id,
                    meeting_id=draft.meeting_id,
                    type=final_payload.get("type", "risk"),
                    description=final_payload.get("description", ""),
                    severity=final_payload.get("severity", "medium"),
                    owner=final_payload.get("owner", "MISSING"),
                    status=final_payload.get("status", "open"),
                    supporting_lines=draft.supporting_lines,
                ))
        else:
            db.add(RaidItem(
                project_id=project.id,
                meeting_id=draft.meeting_id,
                type=final_payload.get("type", "risk"),
                description=final_payload.get("description", ""),
                severity=final_payload.get("severity", "medium"),
                owner=final_payload.get("owner", "MISSING"),
                status=final_payload.get("status", "open"),
                supporting_lines=draft.supporting_lines,
            ))

    elif draft.category == "scope_change":
        db.add(
            ScopeChangeRequest(
                project_id=project.id,
                meeting_id=draft.meeting_id,
                requested_change=final_payload.get("requested_change", ""),
                verbatim_quote=final_payload.get("verbatim_quote", ""),
                supporting_lines=draft.supporting_lines,
                impact_summary=final_payload.get("impact_summary", ""),
                status="approved",
            )
        )

    elif draft.category == "jira_status_update":
        jira_issue_key = final_payload.get("jira_issue_key")
        proposed_status = final_payload.get("proposed_status")
        comment = final_payload.get("comment_to_add")
        try:
            if proposed_status and jira_issue_key:
                await mcp_client.call_tool(
                    "jira",
                    "jira_update_status",
                    {"issue_key": jira_issue_key, "target_status": proposed_status},
                )
            if comment and jira_issue_key:
                await mcp_client.call_tool(
                    "jira",
                    "jira_add_comment",
                    {
                        "issue_key": jira_issue_key,
                        "comment_text": f"[AI PM Agent - Approved by {approver_name}]\n{comment}",
                    },
                )
            jira_sync_status = "synced"
        except Exception as e:
            jira_sync_status = "failed"
            jira_sync_error = str(e)

    audit = AuditHistory(
        draft_id=draft.id,
        project_id=project.id,
        category=draft.category,
        original_draft=original_payload,
        final_approved_content=final_payload,
        approver_name=approver_name,
        approver_role="pm",
        action=action,
        jira_sync_status=jira_sync_status,
        jira_sync_error=jira_sync_error,
        jira_issue_key=jira_issue_key,
    )
    db.add(audit)
    await db.commit()
    await db.refresh(audit)
    return audit


async def reject_draft(
    db: AsyncSession,
    draft: DraftUpdate,
    project: Project,
    approver_name: str = "Project Manager",
) -> AuditHistory:
    """Rejects a DraftUpdate and records the rejection in AuditHistory."""
    draft.status = "rejected"
    audit = AuditHistory(
        draft_id=draft.id,
        project_id=project.id,
        category=draft.category,
        original_draft=dict(draft.proposed_payload),
        final_approved_content=dict(draft.proposed_payload),
        approver_name=approver_name,
        approver_role="pm",
        action="rejected",
        jira_sync_status="not_applicable",
    )
    db.add(audit)
    await db.commit()
    await db.refresh(audit)
    return audit


async def retry_jira_sync(db: AsyncSession, audit: AuditHistory, project: Project) -> AuditHistory:
    """Safely retries a failed Jira write using idempotency protection via MCP Client."""
    payload = audit.final_approved_content

    try:
        if audit.category == "action_item":
            desc = (
                f"{payload.get('description', '')}\n\n"
                f"Owner: {payload.get('owner', 'MISSING')}\n"
                f"Due Date: {payload.get('due_date', 'MISSING')}\n"
                f"Approved by: {audit.approver_name} (Retry)"
            )
            res = await mcp_client.call_tool(
                "jira",
                "jira_create_issue",
                {
                    "project_key": project.jira_project_key,
                    "summary": payload.get("description", "Action Item"),
                    "description": desc,
                    "issue_type": "Task",
                    "idempotency_key": audit.draft_id,
                },
            )
            audit.jira_issue_key = res.get("key")
        elif audit.category == "jira_status_update":
            key = payload.get("jira_issue_key")
            if payload.get("proposed_status") and key:
                await mcp_client.call_tool(
                    "jira",
                    "jira_update_status",
                    {"issue_key": key, "target_status": payload["proposed_status"]},
                )
            if payload.get("comment_to_add") and key:
                await mcp_client.call_tool(
                    "jira",
                    "jira_add_comment",
                    {
                        "issue_key": key,
                        "comment_text": f"[AI PM Agent Retry]\n{payload['comment_to_add']}",
                    },
                )
            audit.jira_issue_key = key

        audit.jira_sync_status = "retried"
        audit.jira_sync_error = None
    except Exception as e:
        audit.jira_sync_status = "failed"
        audit.jira_sync_error = str(e)

    await db.commit()
    await db.refresh(audit)
    return audit
