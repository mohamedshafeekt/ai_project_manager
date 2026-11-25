"""
Initializes database tables on Neon PostgreSQL and seeds the default project.
"""

import asyncio

from sqlalchemy import select

from app.config import settings
from app.db.models import Project, ProjectMember
from app.db.session import AsyncSessionLocal, init_db

DEFAULT_BASELINE_SCOPE = """
Agreed Project Scope - Core Deliverables:
1. User Authentication System: Secure JWT login, OAuth 2.1 integration, and password reset API.
2. Payment Gateway Integration: Stripe checkout, billing subscription management, and webhook handling.
3. User Profile Management: Profile CRUD API, avatar upload, and user preferences.
4. Core Analytics Reporting: Basic dashboard for tracking daily active users and payment transactions.

Explicitly Out of Scope for Phase 1:
- Multi-currency billing and tax calculation engine.
- Real-time video/audio streaming features.
- Custom enterprise SSO (SAML/SCIM) integrations.
- Native mobile applications (iOS/Android).
"""


async def main():
    print("Creating all tables in Neon PostgreSQL...")
    await init_db()
    print("All tables created successfully!")

    async with AsyncSessionLocal() as session:
        # Check if project already exists
        result = await session.execute(
            select(Project).where(Project.jira_project_key == settings.JIRA_PROJECT_KEY)
        )
        existing_proj = result.scalar_one_or_none()

        if not existing_proj:
            project = Project(
                name="Point Zero One Tech Team",
                agreed_scope=DEFAULT_BASELINE_SCOPE.strip(),
                jira_project_key=settings.JIRA_PROJECT_KEY,
                github_repo=settings.clean_github_repo,
            )
            session.add(project)
            await session.flush()

            # Seed members with roles
            pm_member = ProjectMember(
                project_id=project.id,
                name="Mohamed Shafeek",
                email=settings.JIRA_EMAIL or "mohamedshafeekt@gmail.com",
                role="pm"
            )
            dev_member = ProjectMember(
                project_id=project.id,
                name="Alex Developer",
                email="alex.dev@example.com",
                role="team_member"
            )
            sponsor_member = ProjectMember(
                project_id=project.id,
                name="Sarah Sponsor",
                email="sarah.exec@example.com",
                role="sponsor"
            )
            admin_member = ProjectMember(
                project_id=project.id,
                name="System Admin",
                email="admin@example.com",
                role="admin"
            )
            session.add_all([pm_member, dev_member, sponsor_member, admin_member])
            await session.commit()
            print(f"Seeded default Project: '{project.name}' (Key: {project.jira_project_key}) with 4 role-based members.")
        else:
            print(f"Project '{existing_proj.name}' (Key: {existing_proj.jira_project_key}) already exists in database.")

if __name__ == "__main__":
    asyncio.run(main())
