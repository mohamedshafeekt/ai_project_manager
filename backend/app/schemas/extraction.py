"""
Pydantic v2 schemas for structured LLM outputs and API contracts.
Guarantees zero broken AI outputs per PRD Quality rules.
"""

from typing import Literal

from pydantic import BaseModel, Field


# =====================================================================
# 1. Minutes & Decisions Agent Output
# =====================================================================
class ExtractedDecision(BaseModel):
    decision_text: str = Field(description="Clear statement of what was decided by the group.")
    supporting_lines: list[int] = Field(
        description="Exact 1-based line numbers from the transcript that support this decision."
    )


class MinutesExtractionResult(BaseModel):
    summary: str = Field(description="Concise 3-5 sentence executive summary of the meeting.")
    decisions: list[ExtractedDecision] = Field(default_factory=list)


# =====================================================================
# 2. Action Items Agent Output
# =====================================================================
class ExtractedActionItem(BaseModel):
    description: str = Field(description="Specific task that needs to be done.")
    owner: str = Field(
        description="Name of the person responsible. MUST be 'MISSING' if not explicitly stated in the transcript. NEVER guess."
    )
    due_date: str = Field(
        description="Resolved ISO date (YYYY-MM-DD) calculated from the meeting date, or 'MISSING' if no deadline was spoken. NEVER guess."
    )
    supporting_lines: list[int] = Field(
        description="Exact 1-based line numbers from the transcript where this action item was agreed."
    )
    confidence_score: float = Field(ge=0.0, le=1.0, description="Confidence between 0.0 and 1.0.")


class ActionItemsExtractionResult(BaseModel):
    action_items: list[ExtractedActionItem] = Field(default_factory=list)


# =====================================================================
# 3. RAID Log Agent Output
# =====================================================================
class ExtractedRaidItem(BaseModel):
    action_type: Literal["new", "update"] = Field(
        description="'new' if proposing a brand-new RAID entry, 'update' if updating an existing entry."
    )
    existing_raid_id: str | None = Field(
        default=None,
        description="ID of the existing RAID item if action_type is 'update', else null."
    )
    raid_type: Literal["risk", "assumption", "issue", "dependency"]
    description: str = Field(description="Detailed description of the risk, assumption, issue, or dependency.")
    severity: Literal["low", "medium", "high", "critical"]
    owner: str = Field(description="Owner name or 'MISSING' if not stated.")
    status: Literal["open", "mitigated", "closed"] = "open"
    supporting_lines: list[int] = Field(description="Exact 1-based line numbers from the transcript.")
    confidence_score: float = Field(ge=0.0, le=1.0)


class RaidExtractionResult(BaseModel):
    raid_items: list[ExtractedRaidItem] = Field(default_factory=list)


# =====================================================================
# 4. Scope Creep Detection Agent Output
# =====================================================================
class ExtractedScopeChange(BaseModel):
    requested_change: str = Field(description="Description of the new feature/work requested that is outside agreed scope.")
    verbatim_quote: str = Field(description="Exact verbatim quote from the transcript raising this request.")
    supporting_lines: list[int] = Field(description="Exact 1-based line numbers from the transcript.")
    impact_summary: str = Field(description="Likely impact on timeline, effort, or agreed deliverables.")
    confidence_score: float = Field(ge=0.0, le=1.0)


class ScopeChangeExtractionResult(BaseModel):
    scope_changes: list[ExtractedScopeChange] = Field(default_factory=list)


# =====================================================================
# 5. Jira & GitHub Reconciliation Agent Output
# =====================================================================
class ExtractedJiraUpdate(BaseModel):
    jira_issue_key: str = Field(description="Exact key of the existing Jira issue, e.g., 'APM-1'.")
    proposed_status: str | None = Field(
        default=None,
        description="Proposed new Jira status (e.g. 'Done', 'In Progress') if spoken status suggests a change."
    )
    comment_to_add: str = Field(description="Concise comment summarizing what was said in the meeting about this issue.")
    github_evidence: str | None = Field(
        default=None,
        description="Summary of matching GitHub PR/commit state (e.g., 'PR #1 is currently OPEN')."
    )
    has_discrepancy: bool = Field(
        default=False,
        description="True if what was said in the meeting contradicts GitHub reality (e.g., said done while PR is open)."
    )
    discrepancy_note: str | None = Field(
        default=None,
        description="Explanation of the contradiction if has_discrepancy is True."
    )
    supporting_lines: list[int] = Field(description="Exact 1-based line numbers from the transcript.")
    confidence_score: float = Field(ge=0.0, le=1.0)


class ReconciliationResult(BaseModel):
    jira_updates: list[ExtractedJiraUpdate] = Field(default_factory=list)
