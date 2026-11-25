"""
GitHub MCP Connector
Fetches live pull requests, commits, and extracts Jira issue references (e.g., APM-1, KAN-1)
to provide supporting evidence and discrepancy detection (PRD Features 6 & 13).
"""

import re
from typing import Any

import httpx
from langsmith import traceable

from app.config import settings


class GitHubMCPConnector:
    """MCP-compliant read-only connector for GitHub."""

    def __init__(self, repo_override: str | None = None):
        self.token = settings.GITHUB_TOKEN
        self.repo = (repo_override or settings.clean_github_repo).replace("https://github.com/", "").strip("/")
        self.headers = {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    def list_mcp_tools(self) -> list[dict[str, Any]]:
        return [
            {"name": "github_get_pull_requests", "description": "Fetch recent PRs with merge status and Jira key links."},
            {"name": "github_get_commits", "description": "Fetch recent commits on main/default branch."},
        ]

    @staticmethod
    def extract_jira_keys(text: str) -> list[str]:
        """Extracts Jira-style ticket keys (e.g., APM-1, KAN-12) from text."""
        if not text:
            return []
        return list(set(re.findall(r"\b[A-Z]{2,10}-\d+\b", text)))

    @traceable(run_type="tool", name="GitHub: Get Pull Requests")
    async def get_recent_pull_requests(self, limit: int = 20) -> list[dict[str, Any]]:
        """Fetches recent PRs (open, closed, merged) and maps them to Jira keys."""
        if not (self.token and self.repo):
            return []

        url = f"https://api.github.com/repos/{self.repo}/pulls?state=all&sort=updated&direction=desc&per_page={limit}"
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(url, headers=self.headers)
            if resp.status_code != 200:
                raise RuntimeError(f"GitHub PR fetch failed ({resp.status_code}): {resp.text}")

            prs = []
            for pr in resp.json():
                title = pr.get("title", "")
                body = pr.get("body") or ""
                branch = pr.get("head", {}).get("ref", "")
                merged_at = pr.get("merged_at")
                raw_state = pr.get("state", "open")
                effective_state = "merged" if merged_at else raw_state

                linked_keys = self.extract_jira_keys(f"{title} {body} {branch}")
                prs.append({
                    "number": pr.get("number"),
                    "identifier": f"PR #{pr.get('number')}",
                    "title": title,
                    "author": pr.get("user", {}).get("login", "unknown"),
                    "state": effective_state,
                    "branch": branch,
                    "url": pr.get("html_url", ""),
                    "linked_jira_keys": linked_keys,
                    "updated_at": pr.get("updated_at"),
                })
            return prs

    @traceable(run_type="tool", name="GitHub: Get Recent Commits")
    async def get_recent_commits(self, limit: int = 15) -> list[dict[str, Any]]:
        """Fetches recent commits on the default branch."""
        if not (self.token and self.repo):
            return []

        url = f"https://api.github.com/repos/{self.repo}/commits?per_page={limit}"
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(url, headers=self.headers)
            if resp.status_code != 200:
                raise RuntimeError(f"GitHub commits fetch failed ({resp.status_code}): {resp.text}")

            commits = []
            for c in resp.json():
                msg = c.get("commit", {}).get("message", "").splitlines()[0]
                sha = c.get("sha", "")[:7]
                author = c.get("commit", {}).get("author", {}).get("name", "unknown")
                linked_keys = self.extract_jira_keys(msg)
                commits.append({
                    "identifier": f"commit {sha}",
                    "title": msg,
                    "author": author,
                    "state": "committed",
                    "url": c.get("html_url", ""),
                    "linked_jira_keys": linked_keys,
                })
            return commits
