"""
FastAPI REST Endpoints for AI Project Manager Agent.
Supports all 4 role-based views (PM, Team Member, Sponsor, Admin) and all 13 PRD features.
"""

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.models import (
    ActionItem,
    AuditHistory,
    CodeActivityLink,
    Decision,
    DraftUpdate,
    Meeting,
    Project,
    ProjectMember,
    RaidItem,
    ScopeChangeRequest,
    TranscriptLine,
)
from app.db.session import get_db
from app.services.mcp_client import mcp_client
from app.services.review_queue import (
    approve_draft,
    ingest_and_analyze_meeting,
    reject_draft,
    retry_jira_sync,
)
from app.services.watchdog import evaluate_project_health_and_alerts

router = APIRouter(prefix="/api")


# =====================================================================
# Request Schemas
# =====================================================================
class ProjectUpdateReq(BaseModel):
    name: str | None = None
    agreed_scope: str | None = None
    jira_project_key: str | None = None
    github_repo: str | None = None


class MemberCreateReq(BaseModel):
    name: str
    email: str
    role: str = "team_member"


class MeetingIngestReq(BaseModel):
    title: str
    meeting_date: str | None = None  # YYYY-MM-DD
    raw_transcript: str = ""
    is_private: bool = False


class DraftApproveReq(BaseModel):
    approver_name: str = "Mohamed Shafeek (PM)"
    edited_payload: dict[str, Any] | None = None


class BatchApproveReq(BaseModel):
    draft_ids: list[str]
    approver_name: str = "Mohamed Shafeek (PM)"


class ActionItemStatusReq(BaseModel):
    status: str  # todo, in_progress, done


# =====================================================================
# 1. Projects & Admin Routes
# =====================================================================
@router.get("/projects")
async def list_projects(db: AsyncSession = Depends(get_db)):
    projects = (await db.execute(select(Project))).scalars().all()
    results = []
    for p in projects:
        members = (
            await db.execute(select(ProjectMember).where(ProjectMember.project_id == p.id))
        ).scalars().all()
        meetings = (
            await db.execute(select(Meeting).where(Meeting.project_id == p.id))
        ).scalars().all()
        total_cost = sum(m.cost_usd for m in meetings)
        total_tokens = sum(m.token_count for m in meetings)
        results.append({
            "id": p.id,
            "name": p.name,
            "agreed_scope": p.agreed_scope,
            "jira_project_key": p.jira_project_key,
            "github_repo": p.github_repo,
            "total_ai_cost_usd": round(total_cost, 6),
            "total_tokens": total_tokens,
            "members": [
                {"id": m.id, "name": m.name, "email": m.email, "role": m.role}
                for m in members
            ],
        })
    return results


@router.patch("/projects/{project_id}")
async def update_project(project_id: str, body: ProjectUpdateReq, db: AsyncSession = Depends(get_db)):
    project = (await db.execute(select(Project).where(Project.id == project_id))).scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    if body.name is not None:
        project.name = body.name
    if body.agreed_scope is not None:
        project.agreed_scope = body.agreed_scope
    if body.jira_project_key is not None:
        project.jira_project_key = body.jira_project_key
    if body.github_repo is not None:
        project.github_repo = body.github_repo
    await db.commit()
    await db.refresh(project)
    return project


@router.post("/projects/{project_id}/members")
async def add_member(project_id: str, body: MemberCreateReq, db: AsyncSession = Depends(get_db)):
    member = ProjectMember(project_id=project_id, name=body.name, email=body.email, role=body.role)
    db.add(member)
    await db.commit()
    await db.refresh(member)
    return member


@router.get("/admin/connections")
async def check_connections(project_id: str | None = None, db: AsyncSession = Depends(get_db)):
    tool_catalog = await mcp_client.list_all_tools()

    jira_status = {"connected": False, "details": "", "tools": tool_catalog.get("jira", [])}
    try:
        key = settings.JIRA_PROJECT_KEY
        if project_id:
            p = (await db.execute(select(Project).where(Project.id == project_id))).scalar_one_or_none()
            if p:
                key = p.jira_project_key
        issues = await mcp_client.call_tool("jira", "jira_get_issues", {"project_key": key, "max_results": 5})
        jira_status["connected"] = True
        jira_status["details"] = (
            f"Connected via FastMCP to {settings.clean_jira_url} "
            f"(Project: {key}, {len(issues)} issue(s) fetched)"
        )
    except Exception as e:
        jira_status["details"] = str(e)

    gh_status = {"connected": False, "details": "", "tools": tool_catalog.get("github", [])}
    try:
        prs = await mcp_client.call_tool("github", "github_get_pull_requests", {"limit": 5})
        gh_status["connected"] = True
        gh_status["details"] = f"Connected via FastMCP to {settings.clean_github_repo} ({len(prs)} PR(s) fetched)"
    except Exception as e:
        gh_status["details"] = str(e)

    return {
        "jira": jira_status,
        "github": gh_status,
        "teams_upload": {
            "connected": True,
            "details": "Ready via FastMCP (Teams VTT, JSON, or speaker-text transcripts)",
            "tools": tool_catalog.get("teams", []),
        },
    }


# =====================================================================
# 2. Meeting Ingestion & Transcript Routes
# =====================================================================
@router.get("/projects/{project_id}/meetings")
async def list_meetings(project_id: str, db: AsyncSession = Depends(get_db)):
    meetings = (
        await db.execute(
            select(Meeting).where(Meeting.project_id == project_id).order_by(Meeting.created_at.desc())
        )
    ).scalars().all()
    return [
        {
            "id": m.id,
            "title": m.title,
            "meeting_date": m.meeting_date.isoformat() if m.meeting_date else None,
            "attendees": m.attendees,
            "is_private": m.is_private,
            "status": m.status,
            "token_count": m.token_count,
            "cost_usd": m.cost_usd,
        }
        for m in meetings
    ]


@router.post("/projects/{project_id}/meetings")
async def ingest_meeting(project_id: str, body: MeetingIngestReq, db: AsyncSession = Depends(get_db)):
    project = (await db.execute(select(Project).where(Project.id == project_id))).scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    if body.meeting_date:
        try:
            m_date = datetime.strptime(body.meeting_date[:10], "%Y-%m-%d").replace(tzinfo=UTC)
        except ValueError:
            m_date = datetime.now(UTC)
    else:
        m_date = datetime.now(UTC)

    meeting = await ingest_and_analyze_meeting(
        db=db,
        project=project,
        title=body.title,
        meeting_date=m_date,
        raw_transcript=body.raw_transcript,
        is_private=body.is_private,
    )
    return {
        "id": meeting.id,
        "title": meeting.title,
        "status": meeting.status,
        "is_private": meeting.is_private,
        "token_count": meeting.token_count,
        "cost_usd": meeting.cost_usd,
    }


@router.post("/projects/{project_id}/meetings/upload")
async def upload_meeting_file(
    project_id: str,
    title: str = Form(...),
    meeting_date: str | None = Form(None),
    is_private: bool = Form(False),
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    project = (await db.execute(select(Project).where(Project.id == project_id))).scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    raw_bytes = await file.read()
    raw_text = raw_bytes.decode("utf-8", errors="replace")

    if meeting_date:
        try:
            m_date = datetime.strptime(meeting_date[:10], "%Y-%m-%d").replace(tzinfo=UTC)
        except ValueError:
            m_date = datetime.now(UTC)
    else:
        m_date = datetime.now(UTC)

    meeting = await ingest_and_analyze_meeting(
        db=db,
        project=project,
        title=title,
        meeting_date=m_date,
        raw_transcript=raw_text,
        is_private=is_private,
    )
    return {"id": meeting.id, "title": meeting.title, "status": meeting.status}


@router.get("/meetings/{meeting_id}/transcript")
async def get_meeting_transcript(meeting_id: str, db: AsyncSession = Depends(get_db)):
    meeting = (await db.execute(select(Meeting).where(Meeting.id == meeting_id))).scalar_one_or_none()
    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting not found")
    if meeting.is_private:
        return {"is_private": True, "lines": []}

    lines = (
        await db.execute(
            select(TranscriptLine)
            .where(TranscriptLine.meeting_id == meeting_id)
            .order_by(TranscriptLine.line_number.asc())
        )
    ).scalars().all()
    return {
        "is_private": False,
        "meeting_title": meeting.title,
        "lines": [
            {
                "line_number": line.line_number,
                "speaker": line.speaker,
                "timestamp": line.timestamp,
                "text": line.text,
            }
            for line in lines
        ],
    }


# =====================================================================
# 3. Review Queue & Approval Routes
# =====================================================================
@router.get("/projects/{project_id}/drafts")
async def list_drafts(project_id: str, status: str | None = None, db: AsyncSession = Depends(get_db)):
    stmt = select(DraftUpdate).where(DraftUpdate.project_id == project_id)
    if status:
        stmt = stmt.where(DraftUpdate.status == status)
    stmt = stmt.order_by(DraftUpdate.created_at.desc())
    drafts = (await db.execute(stmt)).scalars().all()
    return [
        {
            "id": d.id,
            "meeting_id": d.meeting_id,
            "category": d.category,
            "title": d.title,
            "proposed_payload": d.proposed_payload,
            "supporting_lines": d.supporting_lines,
            "confidence_score": d.confidence_score,
            "discrepancy_note": d.discrepancy_note,
            "status": d.status,
            "created_at": d.created_at.isoformat() if d.created_at else None,
        }
        for d in drafts
    ]


@router.post("/drafts/{draft_id}/approve")
async def approve_draft_endpoint(draft_id: str, body: DraftApproveReq, db: AsyncSession = Depends(get_db)):
    draft = (await db.execute(select(DraftUpdate).where(DraftUpdate.id == draft_id))).scalar_one_or_none()
    if not draft:
        raise HTTPException(status_code=404, detail="Draft not found")
    if draft.status != "waiting":
        raise HTTPException(status_code=400, detail=f"Draft is already {draft.status}")

    project = (await db.execute(select(Project).where(Project.id == draft.project_id))).scalar_one()
    audit = await approve_draft(
        db=db,
        draft=draft,
        project=project,
        approver_name=body.approver_name,
        edited_payload=body.edited_payload,
    )
    return {
        "draft_status": draft.status,
        "audit_id": audit.id,
        "jira_sync_status": audit.jira_sync_status,
        "jira_issue_key": audit.jira_issue_key,
        "jira_sync_error": audit.jira_sync_error,
    }


@router.post("/drafts/{draft_id}/reject")
async def reject_draft_endpoint(draft_id: str, body: DraftApproveReq, db: AsyncSession = Depends(get_db)):
    draft = (await db.execute(select(DraftUpdate).where(DraftUpdate.id == draft_id))).scalar_one_or_none()
    if not draft:
        raise HTTPException(status_code=404, detail="Draft not found")
    project = (await db.execute(select(Project).where(Project.id == draft.project_id))).scalar_one()
    audit = await reject_draft(db=db, draft=draft, project=project, approver_name=body.approver_name)
    return {"draft_status": draft.status, "audit_id": audit.id}


@router.post("/projects/{project_id}/drafts/batch-approve")
async def batch_approve_endpoint(project_id: str, body: BatchApproveReq, db: AsyncSession = Depends(get_db)):
    project = (await db.execute(select(Project).where(Project.id == project_id))).scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    results = []
    for d_id in body.draft_ids:
        draft = (await db.execute(select(DraftUpdate).where(DraftUpdate.id == d_id))).scalar_one_or_none()
        if draft and draft.status == "waiting":
            audit = await approve_draft(db=db, draft=draft, project=project, approver_name=body.approver_name)
            results.append({"draft_id": d_id, "jira_sync_status": audit.jira_sync_status, "jira_issue_key": audit.jira_issue_key})
    return {"approved_count": len(results), "results": results}


@router.get("/projects/{project_id}/audit-history")
async def get_audit_history(project_id: str, db: AsyncSession = Depends(get_db)):
    entries = (
        await db.execute(
            select(AuditHistory)
            .where(AuditHistory.project_id == project_id)
            .order_by(AuditHistory.created_at.desc())
        )
    ).scalars().all()
    return entries


@router.post("/audit-history/{audit_id}/retry-jira")
async def retry_jira_endpoint(audit_id: str, db: AsyncSession = Depends(get_db)):
    audit = (await db.execute(select(AuditHistory).where(AuditHistory.id == audit_id))).scalar_one_or_none()
    if not audit:
        raise HTTPException(status_code=404, detail="Audit entry not found")
    project = (await db.execute(select(Project).where(Project.id == audit.project_id))).scalar_one()
    updated = await retry_jira_sync(db=db, audit=audit, project=project)
    return {
        "jira_sync_status": updated.jira_sync_status,
        "jira_issue_key": updated.jira_issue_key,
        "jira_sync_error": updated.jira_sync_error,
    }


# =====================================================================
# 4. Unified Dashboard & Role-Specific Views
# =====================================================================
@router.get("/projects/{project_id}/dashboard")
async def get_project_dashboard(project_id: str, db: AsyncSession = Depends(get_db)):
    project = (await db.execute(select(Project).where(Project.id == project_id))).scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    action_items = (
        await db.execute(select(ActionItem).where(ActionItem.project_id == project_id).order_by(ActionItem.created_at.desc()))
    ).scalars().all()

    raid_items = (
        await db.execute(select(RaidItem).where(RaidItem.project_id == project_id).order_by(RaidItem.created_at.desc()))
    ).scalars().all()

    scope_changes = (
        await db.execute(select(ScopeChangeRequest).where(ScopeChangeRequest.project_id == project_id).order_by(ScopeChangeRequest.created_at.desc()))
    ).scalars().all()

    code_links = (
        await db.execute(select(CodeActivityLink).where(CodeActivityLink.project_id == project_id))
    ).scalars().all()

    decisions = (
        await db.execute(
            select(Decision)
            .join(Meeting, Decision.meeting_id == Meeting.id)
            .where(Meeting.project_id == project_id)
            .order_by(Decision.created_at.desc())
        )
    ).scalars().all()

    health = await evaluate_project_health_and_alerts(db, project_id)

    # Fetch live Jira issues via MCP Client (graceful fallback if unreachable)
    live_jira = []
    try:
        live_jira = await mcp_client.call_tool(
            "jira", "jira_get_issues", {"project_key": project.jira_project_key, "max_results": 20}
        )
    except Exception:
        pass

    return {
        "project": {
            "id": project.id,
            "name": project.name,
            "jira_project_key": project.jira_project_key,
            "github_repo": project.github_repo,
            "agreed_scope": project.agreed_scope,
        },
        "health_and_alerts": health,
        "action_items": action_items,
        "decisions": decisions,
        "raid_items": raid_items,
        "scope_changes": scope_changes,
        "code_activity": code_links,
        "live_jira_issues": live_jira,
    }


@router.patch("/action-items/{item_id}/status")
async def update_action_item_status(item_id: str, body: ActionItemStatusReq, db: AsyncSession = Depends(get_db)):
    """Team Member View: One-tap status update."""
    item = (await db.execute(select(ActionItem).where(ActionItem.id == item_id))).scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Action item not found")
    if body.status not in ("todo", "in_progress", "done"):
        raise HTTPException(status_code=400, detail="Invalid status")
    item.status = body.status
    await db.commit()
    await db.refresh(item)
    return item
