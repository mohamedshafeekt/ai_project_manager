"""
FastAPI Application Entrypoint for AI Project Manager Agent.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router as api_router
from app.db.session import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Ensure database schema is ready on startup
    await init_db()
    yield


app = FastAPI(
    title="AI Project Manager Agent",
    description="Human-in-the-loop AI Project Manager connected live to Meetings, Jira, and GitHub via MCP & LangGraph.",
    version="1.0.0",
    lifespan=lifespan,
)

# Enable CORS for Vite React frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)


@app.get("/health")
async def health_check():
    return {"status": "ok", "service": "ai-project-manager-backend"}
