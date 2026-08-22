"""
Company Intelligence backend (FastAPI).

Run from the backend/ directory:
    uvicorn app.main:app --reload --port 8000

Requires the standalone MCP server (../mcp) to be running for any data
operation. This process holds NO database credentials — see mcp_client.py.
"""

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.agent.analyzer import run_analysis
from app.agent.planner import run_replanner
from app.api.routes import approvals, chat, dashboard, emails, health
from app.approvals.service import ApprovalService
from app.approvals.store import PlanStore
from app.audit.service import AuditService
from app.config import get_settings
from app.mcp_client import call_tool
from app.sessions import SessionStore

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")

settings = get_settings()

app = FastAPI(title="Company Intelligence Backend", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)


async def _execute_via_mcp(tool_name: str, arguments: dict) -> dict:
    """The ONLY execution path: an MCP tool call, reached only through
    ApprovalService.approve() on an explicitly approved plan."""
    return await call_tool(tool_name, arguments, timeout=settings.mcp_tool_timeout_seconds)


app.state.sessions = SessionStore()
app.state.plan_store = PlanStore(ttl_minutes=settings.approval_ttl_minutes)
app.state.audit = AuditService(log_path=settings.audit_log_path)
app.state.approvals = ApprovalService(
    store=app.state.plan_store,
    audit=app.state.audit,
    sessions=app.state.sessions,
    execute_operation=_execute_via_mcp,
    analyze=run_analysis,
    replan=run_replanner,
)

app.include_router(chat.router, prefix="/api", tags=["chat"])
app.include_router(approvals.router, prefix="/api", tags=["approvals"])
app.include_router(dashboard.router, prefix="/api", tags=["dashboard"])
app.include_router(emails.router, prefix="/api", tags=["emails"])
app.include_router(health.router, prefix="/api", tags=["health"])


@app.get("/")
async def root():
    return {
        "service": "company-intelligence-backend",
        "endpoints": ["/api/chat", "/api/approvals", "/api/health"],
    }
