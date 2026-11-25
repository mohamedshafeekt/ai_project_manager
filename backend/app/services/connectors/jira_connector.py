"""
Jira Cloud MCP Connector
Implements live Jira Cloud REST API v3 integrations including the updated
POST /rest/api/3/search/jql endpoint, issue creation with idempotency,
status transitions, and ADF commenting.
"""

from typing import Any

import httpx
from langsmith import traceable

from app.config import settings


class JiraMCPConnector:
    """MCP-compliant connector for Atlassian Jira Cloud."""

    def __init__(self):
        self.base_url = settings.clean_jira_url
        self.email = (settings.JIRA_EMAIL or "").strip()
        self.token = (settings.JIRA_API_TOKEN or "").strip()
        self.auth = (self.email, self.token)
        self.headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    def list_mcp_tools(self) -> list[dict[str, Any]]:
        """Describes the MCP tools exposed by this connector."""
        return [
            {"name": "jira_get_issues", "description": "Fetch open and recent Jira issues for a project."},
            {"name": "jira_create_issue", "description": "Create a new Jira Task/Story with idempotency protection."},
            {"name": "jira_update_status", "description": "Transition an existing Jira issue to a new workflow status."},
            {"name": "jira_add_comment", "description": "Add a formatted comment to a Jira issue."},
        ]

    @traceable(run_type="tool", name="Jira: Get Project Issues")
    async def get_project_issues(self, project_key: str, max_results: int = 50) -> list[dict[str, Any]]:
        """
        Fetches issues using Jira Cloud's current POST /rest/api/3/search/jql API.
        Explicitly requests fields per v3 JQL optimization requirements.
        """
        if not (self.base_url and self.email and self.token):
            return []

        url = f"{self.base_url}/rest/api/3/search/jql"
        payload = {
            "jql": f"project = {project_key} ORDER BY updated DESC",
            "maxResults": max_results,
            "fields": ["summary", "status", "assignee", "issuetype", "labels", "updated"],
        }

        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(url, json=payload, auth=self.auth, headers=self.headers)
            if resp.status_code != 200:
                raise RuntimeError(f"Jira search failed ({resp.status_code}): {resp.text}")

            data = resp.json()
            issues = []
            for item in data.get("issues", []):
                fields = item.get("fields", {})
                assignee = fields.get("assignee")
                issues.append({
                    "key": item.get("key"),
                    "summary": fields.get("summary", ""),
                    "status": fields.get("status", {}).get("name", "Unknown"),
                    "assignee": assignee.get("displayName") if assignee else "Unassigned",
                    "issue_type": fields.get("issuetype", {}).get("name", "Task"),
                    "labels": fields.get("labels", []),
                })
            return issues

    @traceable(run_type="tool", name="Jira: Create Issue (Idempotent)")
    async def create_issue(
        self,
        project_key: str,
        summary: str,
        description: str,
        issue_type: str = "Task",
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        """
        Creates a new Jira issue. Uses a unique label (idempotency_key) to ensure
        retries never create duplicate tickets (PRD Feature 8).
        """
        async with httpx.AsyncClient(timeout=15.0) as client:
            # 1. Idempotency check if key provided
            if idempotency_key:
                safe_label = f"apm-{idempotency_key[:16]}"
                existing = await self._find_by_label(client, project_key, safe_label)
                if existing:
                    return {
                        "key": existing,
                        "status": "already_exists_idempotent",
                        "url": f"{self.base_url}/browse/{existing}",
                    }
                labels = ["ai-pm-agent", safe_label]
            else:
                labels = ["ai-pm-agent"]

            # 2. Construct Atlassian Document Format (ADF) description
            payload = {
                "fields": {
                    "project": {"key": project_key},
                    "summary": summary[:250],
                    "issuetype": {"name": issue_type},
                    "labels": labels,
                    "description": {
                        "type": "doc",
                        "version": 1,
                        "content": [
                            {
                                "type": "paragraph",
                                "content": [{"type": "text", "text": description}],
                            }
                        ],
                    },
                }
            }

            resp = await client.post(
                f"{self.base_url}/rest/api/3/issue",
                json=payload,
                auth=self.auth,
                headers=self.headers,
            )
            if resp.status_code not in (200, 201):
                raise RuntimeError(f"Jira create_issue failed ({resp.status_code}): {resp.text}")

            created = resp.json()
            key = created.get("key")
            return {
                "key": key,
                "status": "created",
                "url": f"{self.base_url}/browse/{key}",
            }

    async def _find_by_label(self, client: httpx.AsyncClient, project_key: str, label: str) -> str | None:
        """Checks if an issue with the idempotency label already exists."""
        url = f"{self.base_url}/rest/api/3/search/jql"
        payload = {
            "jql": f'project = {project_key} AND labels = "{label}"',
            "maxResults": 1,
            "fields": ["summary"],
        }
        resp = await client.post(url, json=payload, auth=self.auth, headers=self.headers)
        if resp.status_code == 200:
            issues = resp.json().get("issues", [])
            if issues:
                return issues[0].get("key")
        return None

    @traceable(run_type="tool", name="Jira: Update Issue Status")
    async def update_issue_status(self, issue_key: str, target_status: str) -> dict[str, Any]:
        """
        Queries available workflow transitions for the issue and transitions it
        to the matching target_status (case-insensitive).
        """
        async with httpx.AsyncClient(timeout=15.0) as client:
            t_url = f"{self.base_url}/rest/api/3/issue/{issue_key}/transitions"
            resp = await client.get(t_url, auth=self.auth, headers=self.headers)
            if resp.status_code != 200:
                raise RuntimeError(f"Failed to fetch transitions for {issue_key} ({resp.status_code}): {resp.text}")

            transitions = resp.json().get("transitions", [])
            matched_id = None
            available = []
            for t in transitions:
                name = t.get("name", "")
                available.append(name)
                if name.lower() == target_status.strip().lower():
                    matched_id = t.get("id")
                    break

            if not matched_id:
                raise ValueError(
                    f"Status '{target_status}' is not a valid transition for {issue_key}. Available: {available}"
                )

            post_resp = await client.post(
                t_url,
                json={"transition": {"id": matched_id}},
                auth=self.auth,
                headers=self.headers,
            )
            if post_resp.status_code not in (200, 204):
                raise RuntimeError(f"Transition failed ({post_resp.status_code}): {post_resp.text}")

            return {"key": issue_key, "new_status": target_status, "status": "transitioned"}

    @traceable(run_type="tool", name="Jira: Add Comment")
    async def add_comment(self, issue_key: str, comment_text: str) -> dict[str, Any]:
        """Adds an ADF-formatted comment to an existing Jira issue."""
        url = f"{self.base_url}/rest/api/3/issue/{issue_key}/comment"
        payload = {
            "body": {
                "type": "doc",
                "version": 1,
                "content": [
                    {
                        "type": "paragraph",
                        "content": [{"type": "text", "text": comment_text}],
                    }
                ],
            }
        }
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(url, json=payload, auth=self.auth, headers=self.headers)
            if resp.status_code not in (200, 201):
                raise RuntimeError(f"Failed to add comment to {issue_key} ({resp.status_code}): {resp.text}")
            return {"key": issue_key, "status": "comment_added"}
