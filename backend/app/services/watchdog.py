"""
Deadline Watchdog Service (PRD Feature 10).
Monitors open Action Items against the current date, raises overdue alerts
for the owner and Project Manager, and computes the delivery forecast.
"""

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ActionItem, RaidItem


async def evaluate_project_health_and_alerts(db: AsyncSession, project_id: str) -> dict[str, Any]:
    """
    Evaluates open action items and RAID items to generate:
    - Overdue deadline alerts
    - Missing metadata warnings
    - Overall delivery forecast (On Track / At Risk / Delayed)
    """
    today_str = datetime.now(UTC).strftime("%Y-%m-%d")
    today_dt = datetime.strptime(today_str, "%Y-%m-%d")

    items = (
        await db.execute(
            select(ActionItem).where(ActionItem.project_id == project_id)
        )
    ).scalars().all()

    raid_items = (
        await db.execute(
            select(RaidItem).where(
                RaidItem.project_id == project_id,
                RaidItem.status == "open"
            )
        )
    ).scalars().all()

    overdue_alerts: list[dict[str, Any]] = []
    missing_info_warnings: list[dict[str, Any]] = []

    open_count = 0
    done_count = 0

    for item in items:
        if item.status == "done":
            done_count += 1
            continue

        open_count += 1

        if item.owner == "MISSING" or item.due_date == "MISSING":
            missing_info_warnings.append({
                "action_item_id": item.id,
                "description": item.description,
                "owner": item.owner,
                "due_date": item.due_date,
                "message": "Requires PM/Owner assignment or due date clarification.",
            })
            continue

        try:
            due_dt = datetime.strptime(item.due_date[:10], "%Y-%m-%d")
            if due_dt < today_dt:
                days_overdue = (today_dt - due_dt).days
                overdue_alerts.append({
                    "action_item_id": item.id,
                    "description": item.description,
                    "owner": item.owner,
                    "due_date": item.due_date,
                    "days_overdue": days_overdue,
                    "alert_message": f"OVERDUE by {days_overdue} day(s): '{item.description}' assigned to {item.owner} (Due {item.due_date}).",
                })
        except ValueError:
            pass

    high_risks = [r for r in raid_items if r.severity in ("high", "critical")]

    # Compute Forecast
    if len(overdue_alerts) >= 2 or len(high_risks) >= 2:
        forecast_status = "Delayed"
        forecast_reason = f"{len(overdue_alerts)} overdue action item(s) and {len(high_risks)} high/critical RAID item(s)."
    elif len(overdue_alerts) == 1 or len(high_risks) == 1 or len(missing_info_warnings) > 0:
        forecast_status = "At Risk"
        forecast_reason = f"{len(overdue_alerts)} overdue item(s), {len(high_risks)} high risk(s), {len(missing_info_warnings)} item(s) missing owner/date."
    else:
        forecast_status = "On Track"
        forecast_reason = "All scheduled action items are within deadlines with no critical blockers."

    total_items = open_count + done_count
    completion_pct = round((done_count / total_items) * 100, 1) if total_items > 0 else 0.0

    return {
        "forecast_status": forecast_status,
        "forecast_reason": forecast_reason,
        "completion_percentage": completion_pct,
        "total_action_items": total_items,
        "completed_action_items": done_count,
        "open_action_items": open_count,
        "overdue_alerts": overdue_alerts,
        "missing_info_warnings": missing_info_warnings,
        "open_high_risks": len(high_risks),
    }
