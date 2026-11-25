# AI Project Manager Agent

A human-in-the-loop **AI Project Manager Agent** that ingests meeting transcripts, cross-references live **Jira Cloud** issues and **GitHub** pull requests/commits via custom **FastMCP** connectors, and drafts structured updates (Minutes, Decisions, Action Items, RAID Log, Scope Change Requests, and Jira Status Updates) using a parallel **LangGraph Scatter-Gather** multi-agent pipeline.

**Core Guarantee:** Nothing reaches Jira or external systems without explicit Project Manager approval.

> **Live App (Netlify):** https://ai-project-manager-poz.netlify.app/  
> **Live API (Render):** https://ai-project-manager-j6n1.onrender.com  
> **Quick Demo Video:** [Click here](https://drive.google.com/file/d/1uEXVjfutXLlOECKsYU3kleRsp2-p48dr/view?usp=sharing)

---

## Key Innovations & Engineering Highlights

1. **Parallel LangGraph Scatter-Gather Multi-Agent Pipeline (`StateGraph`)**
   - Instead of a single monolithic prompt, 5 specialist agents run **concurrently** (`minutes_node`, `action_items_node`, `raid_node`, `scope_node`, `reconciliation_node`) and fan into a **`synthesizer_node`** that cross-checks discrepancies, missing metadata, and overlapping transcript lines.
   - Cuts processing latency while keeping each agent's prompt focused and high-precision.

2. **Custom FastMCP Servers & Unified MCP Client (`ProjectMCPClient`)**
   - Live integrations with **Jira Cloud**, **GitHub**, and **Teams/Transcripts** are built as standalone **FastMCP** servers (`app/mcp_servers/jira_server.py`, `github_server.py`, `teams_server.py`) communicating over the **Model Context Protocol (MCP)**.
   - `ProjectMCPClient` (`app/services/mcp_client.py`) invokes these servers via `fastmcp.Client` and also exposes them as LangChain `StructuredTool`s.

3. **Full LangSmith Observability & Visible AI Cost**
   - Every LangGraph node, LLM call, and MCP tool invocation is instrumented with **LangSmith** (`@traceable`).
   - Exact token usage and USD cost are calculated per meeting and aggregated per project directly in the PM and Sponsor views.

4. **Provider-Agnostic LLM Failover & Strict Structured Outputs**
   - `LLMService` (`app/services/llm/client.py`) enforces **Pydantic v2** schemas via `.with_structured_output(..., include_raw=True)` so malformed AI output is rejected before reaching the database.
   - Supports **OpenAI** (`ChatOpenAI`) as primary with automatic failover to **OpenRouter** (`ChatOpenRouter`) and **Groq**.

5. **Zero-Hallucination Guardrails & GitHub Reality Checks**
   - **Line-Level Citations:** Every draft stores `supporting_lines` linking back to exact transcript lines (viewable in the UI's Transcript Drawer).
   - **Never Guess:** Unspoken action item owners or due dates are strictly recorded as `"MISSING"` rather than hallucinated.
   - **Discrepancy Alerts:** The Reconciliation Agent checks whether a spoken *"done"* claim matches GitHub reality, raising a warning if the linked Pull Request is still `OPEN`.

6. **Idempotent Jira Writes & Audit Trail**
   - Approved drafts create Jira issues tagged with a unique `apm-<draft_id>` idempotency label so retrying a failed sync never creates duplicate tickets.
   - Every approval, inline edit (original vs. final JSON diff), rejection, and Jira sync status is logged in `AuditHistory`.

---

## Architecture & Tech Stack

- **Backend:** FastAPI (Python 3.12+), SQLAlchemy (async), Alembic migrations, Pydantic v2.
- **Database:** Managed PostgreSQL on Neon (`neondb`) with `asyncpg`.
- **AI Orchestration:** LangGraph `StateGraph` (5 parallel specialist agents + fan-in Synthesizer).
- **Connectors:** 3 custom FastMCP servers (`jira-mcp-server`, `github-mcp-server`, `teams-mcp-server`) + `ProjectMCPClient`.
- **Observability & Evaluation:** LangSmith (`@traceable`) + `pytest` ground-truth accuracy benchmark (`tests/test_accuracy_benchmark.py`, `tests/test_mcp_and_synthesizer.py`).
- **Frontend:** React + Vite + Tailwind CSS with 4 role-based views (**Project Manager**, **Team Member**, **Sponsor**, **Admin**) and a **Transcript Citation Drawer**.

---

## PRD Coverage (13 Features & 4 Role Views)

- **4 Role-Based Views:**
  - **Project Manager:** Ingest transcripts, review/edit/approve/reject/batch-approve drafts, inspect source citations, monitor AI cost, and retry failed Jira syncs.
  - **Team Member:** Filter personal action items and update status (`To Do` → `In Progress` → `Done`) in one tap.
  - **Sponsor:** Read-only executive dashboard with Delivery Forecast (`On Track` / `At Risk` / `Delayed`), completion %, open high risks, overdue alerts, and total AI spend.
  - **Admin:** Live MCP connector health & exposed tool catalog, project Jira/GitHub settings, and the **Agreed Scope Baseline** editor.
- **All 13 First-Release Features:** Meeting ingestion, Minutes & Decisions, Action Items (relative date resolution + `MISSING` sentinels), RAID Log (new & updates to existing items), Scope Creep Detection, Jira/GitHub Reconciliation, PM Review Queue, Idempotent Jira Writes, Role Views, Deadline Watchdog & Alerts, Change/Audit History, Private Meetings (`private_skipped`, never read or stored), and Code Progress Tracking.

---

## Repository Structure

```text
ai_project_manager/
├── backend/
│   ├── app/
│   │   ├── api/routes.py                  # FastAPI REST endpoints
│   │   ├── db/models.py                   # SQLAlchemy models (Project, Meeting, DraftUpdate, AuditHistory, etc.)
│   │   ├── mcp_servers/                   # Custom FastMCP servers (Jira, GitHub, Teams)
│   │   ├── schemas/extraction.py          # Strict Pydantic v2 schemas for agent outputs
│   │   └── services/
│   │       ├── agents/graph.py            # LangGraph Scatter-Gather pipeline (5 agents + Synthesizer)
│   │       ├── connectors/                # Live Jira Cloud, GitHub, and transcript parsers
│   │       ├── llm/client.py              # Provider-agnostic LLM service + failover + cost tracking
│   │       ├── mcp_client.py              # Unified FastMCP client & LangChain StructuredTool adapter
│   │       ├── review_queue.py            # Human-in-the-loop approval & idempotent Jira sync
│   │       └── watchdog.py                # Deadline alerts & delivery forecast engine
│   ├── scripts/                           # DB init & live connection verification scripts
│   └── tests/                             # Accuracy benchmark & MCP/synthesizer tests
└── frontend/
    └── src/
        ├── App.jsx                        # Role switcher & main shell
        ├── components/TranscriptDrawer.jsx# Line-level citation drawer
        └── views/                         # PMView, MemberView, SponsorView, AdminView
```

---

## Meeting Source Choice

Per Part 2 of the PRD (*"If Teams transcription isn't available to you"*):
- **Option chosen:** **Transcript Upload & Ingestion** (supporting Microsoft Teams `.vtt` WebVTT exports, `.json`, and speaker-timestamped text).
- **Why:** Microsoft Teams live transcription requires a paid Microsoft 365 Enterprise/Business license. Supporting `.vtt` and structured transcript uploads ensures identical downstream behavior (speaker attribution, timestamps, line-level citations) while remaining immediately reproducible.

---

## Setup & Running Locally

### 1. Environment Variables (`.env`)
Configure `.env` in the project root:
```env
DATABASE_URL="postgresql://neondb_owner:<password>@<host>.neon.tech/neondb?sslmode=require"

JIRA_URL="https://your-domain.atlassian.net"
JIRA_EMAIL="your-email@example.com"
JIRA_API_TOKEN="your_atlassian_api_token"
JIRA_PROJECT_KEY="APM"

GITHUB_TOKEN="ghp_your_token"
GITHUB_REPO="your-username/your-repo"

OPENAI_API_KEY="sk-your-openai-key"
GROQ_API_KEY="gsk-optional-fallback"
OPENROUTER_API_KEY="sk-or-optional-fallback"

LANGSMITH_TRACING="true"
LANGSMITH_API_KEY="lsv2_your_langsmith_key"
LANGSMITH_PROJECT="apm"
```

### 2. Backend Setup
```powershell
cd backend

# Install Python dependencies
uv sync --link-mode=copy

# Initialize database tables & seed default project
uv run python -m scripts.init_database
uv run alembic stamp head

# Verify live connections (Neon, Jira, GitHub, OpenAI/LangSmith)
uv run python -m scripts.test_connections

# Start FastAPI backend
uv run uvicorn app.main:app --reload --port 8000
```

### 3. Frontend Setup
```powershell
cd frontend
npm install
npm.cmd run dev
```
Open **[http://localhost:5173](http://localhost:5173)**.

### 4. Run Accuracy Benchmark Suite
```powershell
cd backend
uv run pytest -v
```

---

## Key Assumptions

1. **Single Organization, Multi-Project Ready:** Data models are scoped by `project_id` so multiple projects can coexist cleanly within one organization.
2. **Role Switching Without Full SSO:** Authentication is modeled via explicit role selection (`Project Manager`, `Team Member`, `Sponsor`, `Admin`) as permitted in Part 2 (*"Sign-in can be simple, as long as each user's role is enforced"*).
3. **Jira Cloud v3 Search Endpoint:** Uses Atlassian's current `POST /rest/api/3/search/jql` API (replacing the deprecated `/rest/api/3/search` endpoint) with explicit field selection.
4. **Idempotent Jira Writes:** Every newly created Jira issue includes a unique `apm-<draft_id>` label so retrying failed writes never creates duplicate tickets.
5. **Zero Guessing Policy:** If an action item owner or due date is not spoken in the transcript, the agent records `"MISSING"` rather than guessing.
