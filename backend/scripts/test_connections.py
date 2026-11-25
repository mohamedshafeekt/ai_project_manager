"""
AI Project Manager Agent - Environment Verification Script
Tests all 4 required integrations:
1. Neon PostgreSQL
2. Jira Cloud API
3. GitHub REST API
4. OpenAI API & LangSmith Tracing
"""

import asyncio
import os
import re
import urllib.parse

from dotenv import load_dotenv

load_dotenv(override=True)


async def test_database():
    print("\n--- 1. Testing Neon PostgreSQL Connection ---")
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        print("[FAIL] DATABASE_URL is not set in .env")
        return False

    try:
        from sqlalchemy import text
        from sqlalchemy.ext.asyncio import create_async_engine

        # Parse & normalize for asyncpg (strip parameters not supported by asyncpg connect)
        u = urllib.parse.urlsplit(db_url.strip())
        q = urllib.parse.parse_qs(u.query)
        q.pop("channel_binding", None)
        q.pop("sslmode", None)
        q["ssl"] = ["require"]
        clean_query = urllib.parse.urlencode(q, doseq=True)
        async_url = urllib.parse.urlunsplit(("postgresql+asyncpg", u.netloc, u.path, clean_query, ""))

        engine = create_async_engine(async_url, echo=False)
        async with engine.connect() as conn:
            result = await conn.execute(text("SELECT current_database(), current_user, version();"))
            row = result.fetchone()
            print("[SUCCESS] Connected to PostgreSQL on Neon!")
            print(f"          Database: {row[0]}")
            print(f"          User: {row[1]}")
            print(f"          Engine: {row[2][:35]}...")
        await engine.dispose()
        return True
    except Exception as e:
        print(f"[FAIL] Database connection error: {e}")
        return False


async def test_jira():
    print("\n--- 2. Testing Jira Cloud Connection ---")
    import httpx

    raw_jira_url = os.getenv("JIRA_URL", "").strip()
    jira_email = os.getenv("JIRA_EMAIL", "").strip()
    jira_token = os.getenv("JIRA_API_TOKEN", "").strip()
    jira_key = os.getenv("JIRA_PROJECT_KEY", "APM").strip()

    if not (raw_jira_url and jira_email and jira_token):
        print("[FAIL] JIRA_URL, JIRA_EMAIL, or JIRA_API_TOKEN missing in .env")
        return False

    # Extract base domain, e.g. https://mohamedshafeekt.atlassian.net
    match = re.search(r"https?://[^/]+", raw_jira_url)
    jira_base_url = match.group(0) if match else raw_jira_url.rstrip("/")

    auth = (jira_email, jira_token)
    headers = {"Accept": "application/json", "Content-Type": "application/json"}

    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            # 1. Fetch user info
            user_resp = await client.get(f"{jira_base_url}/rest/api/3/myself", auth=auth, headers=headers)
            if user_resp.status_code == 200:
                user = user_resp.json()
                print(f"[SUCCESS] Authenticated with Jira as: {user.get('displayName')} ({user.get('emailAddress')})")
            else:
                print(f"[FAIL] Jira auth returned status {user_resp.status_code}: {user_resp.text}")
                return False

            # 2. Fetch project info
            proj_url = f"{jira_base_url}/rest/api/3/project/{jira_key}"
            resp = await client.get(proj_url, auth=auth, headers=headers)
            if resp.status_code == 200:
                data = resp.json()
                print(f"[SUCCESS] Jira Project Verified: {data.get('name')} (Key: {data.get('key')})")
            else:
                print(f"[WARN] Project {jira_key} lookup returned status {resp.status_code}: {resp.text[:200]}")

            # 3. Search issues using POST (v3 standard)
            search_url = f"{jira_base_url}/rest/api/3/search"
            payload = {"jql": f"project = {jira_key}", "maxResults": 10}
            search_resp = await client.post(search_url, json=payload, auth=auth, headers=headers)
            if search_resp.status_code == 200:
                issues = search_resp.json().get("issues", [])
                print(f"[SUCCESS] Found {len(issues)} issue(s) in Jira project {jira_key}:")
                for issue in issues[:5]:
                    key = issue.get("key")
                    summary = issue.get("fields", {}).get("summary", "No summary")
                    status = issue.get("fields", {}).get("status", {}).get("name", "Unknown")
                    print(f"          - [{key}] {summary} (Status: {status})")
            elif search_resp.status_code == 410:
                # Fallback to GET /rest/api/2/search
                search_v2 = f"{jira_base_url}/rest/api/2/search?jql=project={jira_key}&maxResults=10"
                s2_resp = await client.get(search_v2, auth=auth, headers={"Accept": "application/json"})
                if s2_resp.status_code == 200:
                    issues = s2_resp.json().get("issues", [])
                    print(f"[SUCCESS] Found {len(issues)} issue(s) in Jira project {jira_key}:")
                    for issue in issues[:5]:
                        key = issue.get("key")
                        summary = issue.get("fields", {}).get("summary", "No summary")
                        status = issue.get("fields", {}).get("status", {}).get("name", "Unknown")
                        print(f"          - [{key}] {summary} (Status: {status})")
            return True
        except Exception as e:
            print(f"[FAIL] Jira request failed: {e}")
            return False


async def test_github():
    print("\n--- 3. Testing GitHub REST API ---")
    import httpx

    token = os.getenv("GITHUB_TOKEN", "").strip()
    raw_repo = os.getenv("GITHUB_REPO", "").strip()

    if not (token and raw_repo):
        print("[FAIL] GITHUB_TOKEN or GITHUB_REPO missing in .env")
        return False

    # Clean repo name if full URL was provided
    repo = raw_repo.replace("https://github.com/", "").strip("/")

    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            # 1. Repo info
            repo_url = f"https://api.github.com/repos/{repo}"
            resp = await client.get(repo_url, headers=headers)
            if resp.status_code == 200:
                data = resp.json()
                print(f"[SUCCESS] GitHub Repo Connected: {data.get('full_name')} (Private: {data.get('private')})")
            else:
                print(f"[FAIL] GitHub repo check returned {resp.status_code}: {resp.text}")
                return False

            # 2. Pull requests
            prs_url = f"https://api.github.com/repos/{repo}/pulls?state=all&per_page=5"
            prs_resp = await client.get(prs_url, headers=headers)
            if prs_resp.status_code == 200:
                prs = prs_resp.json()
                print(f"[SUCCESS] Found {len(prs)} PR(s) in {repo}:")
                for pr in prs:
                    print(f"          - PR #{pr.get('number')}: {pr.get('title')} (State: {pr.get('state')})")
                return True
            return True
        except Exception as e:
            print(f"[FAIL] GitHub request failed: {e}")
            return False


async def test_openai_and_langsmith():
    print("\n--- 4. Testing OpenAI API & LangSmith ---")
    from openai import AsyncOpenAI

    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        print("[FAIL] OPENAI_API_KEY missing in .env")
        return False

    ls_tracing = os.getenv("LANGCHAIN_TRACING_V2") or os.getenv("LANGSMITH_TRACING")
    ls_project = os.getenv("LANGCHAIN_PROJECT") or os.getenv("LANGSMITH_PROJECT")
    print(f"          LangSmith Tracing: {ls_tracing} | Project: {ls_project}")

    try:
        client = AsyncOpenAI(api_key=api_key)
        response = await client.chat.completions.create(
            model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
            messages=[{"role": "user", "content": "Respond with: PING_OK"}],
            max_tokens=10,
        )
        content = response.choices[0].message.content
        print(f"[SUCCESS] OpenAI API responded: '{content.strip()}'")
        return True
    except Exception as e:
        print(f"[FAIL] OpenAI API request failed: {e}")
        return False


async def main():
    print("=" * 60)
    print("AI Project Manager Agent - Environment Verification")
    print("=" * 60)

    db_ok = await test_database()
    jira_ok = await test_jira()
    github_ok = await test_github()
    ai_ok = await test_openai_and_langsmith()

    print("\n" + "=" * 60)
    print("SUMMARY:")
    print(f"1. Neon PostgreSQL: {'[PASS]' if db_ok else '[FAIL]'}")
    print(f"2. Jira Cloud:      {'[PASS]' if jira_ok else '[FAIL]'}")
    print(f"3. GitHub:          {'[PASS]' if github_ok else '[FAIL]'}")
    print(f"4. OpenAI / Trace:  {'[PASS]' if ai_ok else '[FAIL]'}")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
