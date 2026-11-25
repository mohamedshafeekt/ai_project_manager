import uuid
from datetime import UTC, datetime

from sqlalchemy import JSON, Boolean, Column, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    pass


def utcnow() -> datetime:
    return datetime.now(UTC)


class Project(Base):
    """Represents a project, its agreed scope baseline, and linked systems."""
    __tablename__ = "projects"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(255), nullable=False)
    agreed_scope = Column(Text, nullable=False, default="")  # Baseline scope description
    jira_project_key = Column(String(32), nullable=False, default="APM")
    github_repo = Column(String(255), nullable=False, default="")
    created_at = Column(DateTime(timezone=True), default=utcnow)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    # Relationships
    members = relationship("ProjectMember", back_populates="project", cascade="all, delete-orphan")
    meetings = relationship("Meeting", back_populates="project", cascade="all, delete-orphan")
    action_items = relationship("ActionItem", back_populates="project", cascade="all, delete-orphan")
    raid_items = relationship("RaidItem", back_populates="project", cascade="all, delete-orphan")
    scope_changes = relationship("ScopeChangeRequest", back_populates="project", cascade="all, delete-orphan")
    drafts = relationship("DraftUpdate", back_populates="project", cascade="all, delete-orphan")
    code_links = relationship("CodeActivityLink", back_populates="project", cascade="all, delete-orphan")


class ProjectMember(Base):
    """Team members and their roles (PM, Team member, Sponsor, Admin)."""
    __tablename__ = "project_members"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id = Column(String(36), ForeignKey("projects.id"), nullable=False, index=True)
    name = Column(String(128), nullable=False)
    email = Column(String(128), nullable=False, index=True)
    role = Column(String(32), nullable=False, default="team_member")  # pm, team_member, sponsor, admin
    created_at = Column(DateTime(timezone=True), default=utcnow)

    project = relationship("Project", back_populates="members")


class Meeting(Base):
    """Represents a project meeting ingested from Teams, audio, or transcript upload."""
    __tablename__ = "meetings"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id = Column(String(36), ForeignKey("projects.id"), nullable=False, index=True)
    title = Column(String(255), nullable=False)
    meeting_date = Column(DateTime(timezone=True), default=utcnow)
    attendees = Column(JSON, default=list)  # list of speaker/attendee names
    is_private = Column(Boolean, default=False)  # PRD Feature 12: Private meetings
    raw_transcript = Column(Text, nullable=False, default="")
    status = Column(String(32), default="pending")  # pending, analyzed, private_skipped
    token_count = Column(Integer, default=0)
    cost_usd = Column(Float, default=0.0)  # PRD: Visible AI cost per meeting
    created_at = Column(DateTime(timezone=True), default=utcnow)

    project = relationship("Project", back_populates="meetings")
    lines = relationship("TranscriptLine", back_populates="meeting", cascade="all, delete-orphan")
    decisions = relationship("Decision", back_populates="meeting", cascade="all, delete-orphan")
    action_items = relationship("ActionItem", back_populates="meeting", cascade="all, delete-orphan")
    drafts = relationship("DraftUpdate", back_populates="meeting", cascade="all, delete-orphan")


class TranscriptLine(Base):
    """Verbatim lines of the meeting for strict citation and deep-linking."""
    __tablename__ = "transcript_lines"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    meeting_id = Column(String(36), ForeignKey("meetings.id"), nullable=False, index=True)
    line_number = Column(Integer, nullable=False, index=True)
    speaker = Column(String(128), nullable=False)
    timestamp = Column(String(32), default="")  # e.g. "04:15"
    text = Column(Text, nullable=False)

    meeting = relationship("Meeting", back_populates="lines")


class Decision(Base):
    """Decisions agreed in the meeting, backed by source transcript lines."""
    __tablename__ = "decisions"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    meeting_id = Column(String(36), ForeignKey("meetings.id"), nullable=False, index=True)
    decision_text = Column(Text, nullable=False)
    supporting_lines = Column(JSON, default=list)  # [line_numbers]
    created_at = Column(DateTime(timezone=True), default=utcnow)

    meeting = relationship("Meeting", back_populates="decisions")


class ActionItem(Base):
    """Action items extracted from meetings or created upon draft approval."""
    __tablename__ = "action_items"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id = Column(String(36), ForeignKey("projects.id"), nullable=False, index=True)
    meeting_id = Column(String(36), ForeignKey("meetings.id"), nullable=True, index=True)
    description = Column(Text, nullable=False)
    owner = Column(String(128), nullable=False)  # Name or "MISSING"
    due_date = Column(String(32), nullable=False)  # ISO Date YYYY-MM-DD or "MISSING"
    status = Column(String(32), default="todo")  # todo, in_progress, done
    supporting_lines = Column(JSON, default=list)
    jira_issue_key = Column(String(32), nullable=True)  # e.g. "APM-12"
    created_at = Column(DateTime(timezone=True), default=utcnow)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    project = relationship("Project", back_populates="action_items")
    meeting = relationship("Meeting", back_populates="action_items")


class RaidItem(Base):
    """Risks, Assumptions, Issues, Dependencies (RAID log)."""
    __tablename__ = "raid_items"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id = Column(String(36), ForeignKey("projects.id"), nullable=False, index=True)
    meeting_id = Column(String(36), ForeignKey("meetings.id"), nullable=True)
    type = Column(String(32), nullable=False)  # risk, assumption, issue, dependency
    description = Column(Text, nullable=False)
    severity = Column(String(32), default="medium")  # low, medium, high, critical
    owner = Column(String(128), default="MISSING")
    status = Column(String(32), default="open")  # open, mitigated, closed
    supporting_lines = Column(JSON, default=list)
    created_at = Column(DateTime(timezone=True), default=utcnow)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    project = relationship("Project", back_populates="raid_items")


class ScopeChangeRequest(Base):
    """Scope creep detection: flagged against agreed baseline scope."""
    __tablename__ = "scope_change_requests"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id = Column(String(36), ForeignKey("projects.id"), nullable=False, index=True)
    meeting_id = Column(String(36), ForeignKey("meetings.id"), nullable=True)
    requested_change = Column(Text, nullable=False)
    verbatim_quote = Column(Text, nullable=False)
    supporting_lines = Column(JSON, default=list)
    impact_summary = Column(Text, default="")
    status = Column(String(32), default="pending_review")  # pending_review, approved, rejected
    created_at = Column(DateTime(timezone=True), default=utcnow)

    project = relationship("Project", back_populates="scope_changes")


class DraftUpdate(Base):
    """Central Review Queue entity: All AI proposals waiting for PM approval."""
    __tablename__ = "draft_updates"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id = Column(String(36), ForeignKey("projects.id"), nullable=False, index=True)
    meeting_id = Column(String(36), ForeignKey("meetings.id"), nullable=False, index=True)
    category = Column(String(32), nullable=False)  # action_item, decision, raid_item, scope_change, jira_status_update
    title = Column(String(255), nullable=False)
    proposed_payload = Column(JSON, nullable=False)  # Typed details of what to create/update
    supporting_lines = Column(JSON, default=list)  # Line numbers cited
    confidence_score = Column(Float, default=1.0)  # 0.0 to 1.0
    discrepancy_note = Column(Text, nullable=True)  # e.g. "Spoken done vs GitHub open PR"
    status = Column(String(32), default="waiting")  # waiting, approved, edited, rejected
    created_at = Column(DateTime(timezone=True), default=utcnow)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    project = relationship("Project", back_populates="drafts")
    meeting = relationship("Meeting", back_populates="drafts")


class AuditHistory(Base):
    """PRD Feature 11: Change History and Compliance Log."""
    __tablename__ = "audit_history"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    draft_id = Column(String(36), nullable=False, index=True)
    project_id = Column(String(36), ForeignKey("projects.id"), nullable=False, index=True)
    category = Column(String(32), nullable=False)
    original_draft = Column(JSON, nullable=False)
    final_approved_content = Column(JSON, nullable=False)
    approver_name = Column(String(128), default="Project Manager")
    approver_role = Column(String(32), default="pm")
    action = Column(String(32), default="approved")  # approved, edited_and_approved, rejected
    jira_sync_status = Column(String(32), default="not_applicable")  # not_applicable, synced, failed, retried
    jira_sync_error = Column(Text, nullable=True)
    jira_issue_key = Column(String(32), nullable=True)
    created_at = Column(DateTime(timezone=True), default=utcnow)


class CodeActivityLink(Base):
    """PRD Feature 13: Track code progress and cross-reference with Jira."""
    __tablename__ = "code_activity_links"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id = Column(String(36), ForeignKey("projects.id"), nullable=False, index=True)
    repo_name = Column(String(255), nullable=False)
    activity_type = Column(String(32), default="pull_request")  # pull_request, commit, branch
    identifier = Column(String(64), nullable=False)  # "PR #1" or commit sha
    title = Column(String(255), nullable=False)
    author = Column(String(128), default="")
    state = Column(String(32), default="open")  # open, merged, closed
    jira_issue_key = Column(String(32), nullable=True, index=True)
    has_discrepancy = Column(Boolean, default=False)
    discrepancy_details = Column(Text, nullable=True)
    last_checked_at = Column(DateTime(timezone=True), default=utcnow)

    project = relationship("Project", back_populates="code_links")
