import os
import re
import urllib.parse
from pathlib import Path

from pydantic import Field, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict

_ROOT_ENV = Path(__file__).resolve().parents[2] / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(_ROOT_ENV, ".env"),
        env_file_encoding="utf-8",
        extra="ignore"
    )

    # Database
    DATABASE_URL: str = Field(default="")

    # Jira
    JIRA_URL: str = Field(default="")
    JIRA_EMAIL: str = Field(default="")
    JIRA_API_TOKEN: str = Field(default="")
    JIRA_PROJECT_KEY: str = Field(default="APM")

    # GitHub
    GITHUB_TOKEN: str = Field(default="")
    GITHUB_REPO: str = Field(default="")

    # LLM Settings
    OPENAI_API_KEY: str = Field(default="")
    OPENAI_MODEL: str = Field(default="gpt-6-luna")
    GROQ_API_KEY: str = Field(default="")
    GROQ_MODEL: str = Field(default="llama-3.3-70b-versatile")
    OPENROUTER_API_KEY: str = Field(default="")
    OPENROUTER_MODEL: str = Field(default="anthropic/claude-sonnet-4-5")

    # Observability & Tracing (LangSmith)
    LANGCHAIN_TRACING_V2: str = Field(default="true")
    LANGSMITH_API_KEY: str = Field(default="")
    LANGSMITH_PROJECT: str = Field(default="apm")

    # App
    APP_ENV: str = Field(default="development")
    SECRET_KEY: str = Field(default="dev-secret-key-point-one-zero")

    @computed_field
    @property
    def clean_database_url(self) -> str:
        """
        Normalizes connection string for SQLAlchemy asyncpg:
        - Replaces postgres:// or postgresql:// with postgresql+asyncpg://
        - Strips channel_binding and sslmode which asyncpg doesn't take directly in connect()
        - Enforces ssl=require for Neon cloud PostgreSQL
        """
        raw = self.DATABASE_URL.strip()
        if not raw:
            return "sqlite+aiosqlite:///./apm.db"

        u = urllib.parse.urlsplit(raw)
        q = urllib.parse.parse_qs(u.query)
        q.pop("channel_binding", None)
        q.pop("sslmode", None)
        q["ssl"] = ["require"]
        clean_query = urllib.parse.urlencode(q, doseq=True)
        return urllib.parse.urlunsplit(("postgresql+asyncpg", u.netloc, u.path, clean_query, ""))

    @computed_field
    @property
    def clean_jira_url(self) -> str:
        """Extracts the base domain (e.g. https://domain.atlassian.net) even if a board URL was pasted."""
        match = re.search(r"https?://[^/]+", self.JIRA_URL.strip())
        return match.group(0) if match else self.JIRA_URL.strip().rstrip("/")

    @computed_field
    @property
    def clean_github_repo(self) -> str:
        """Extracts 'owner/repo' even if a full https://github.com/ URL was pasted."""
        return self.GITHUB_REPO.strip().replace("https://github.com/", "").strip("/")


settings = Settings()

# Ensure LangSmith and provider API keys are exported in os.environ
if settings.OPENAI_API_KEY:
    os.environ["OPENAI_API_KEY"] = settings.OPENAI_API_KEY
if settings.OPENROUTER_API_KEY:
    os.environ["OPENROUTER_API_KEY"] = settings.OPENROUTER_API_KEY
if settings.LANGSMITH_API_KEY:
    os.environ["LANGCHAIN_API_KEY"] = settings.LANGSMITH_API_KEY
    os.environ["LANGCHAIN_TRACING_V2"] = settings.LANGCHAIN_TRACING_V2
    os.environ["LANGCHAIN_PROJECT"] = settings.LANGSMITH_PROJECT
