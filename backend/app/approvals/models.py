"""Shared pydantic models: what the planner LLM emits, and how plans are
stored server-side. Kept free of any agents-SDK imports so the approval
workflow (and its tests) never depend on the LLM stack."""

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


class PlannedOperation(BaseModel):
    """One data-access step the agent wants to run. Every field is present
    (nullable where unused) so this works as a strict structured output."""

    type: Literal["query_database", "search_emails"]
    description: str
    # for type == "query_database"
    sql: str | None
    # for type == "search_emails"
    query: str | None
    date_from: str | None
    date_to: str | None
    limit: int


class PlannerOutput(BaseModel):
    """Structured output of the planning agent (spec section 26)."""

    status: Literal["answer", "needs_approval", "needs_clarification"]
    answer: str | None
    clarification_question: str | None
    intent: str | None
    human_explanation: str | None
    operations: list[PlannedOperation]


class AnalysisOutput(BaseModel):
    """Structured output of the analysis agent."""

    answer: str
    evidence: list[str]


class PlanStatus(str, Enum):
    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"
    REJECTED = "rejected"
    EDITED = "edited"
    EXECUTING = "executing"
    COMPLETED = "completed"
    FAILED = "failed"
    EXPIRED = "expired"


def _now() -> datetime:
    return datetime.now(timezone.utc)


class QueryPlan(BaseModel):
    plan_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    session_id: str
    question: str
    intent: str
    human_explanation: str
    operations: list[PlannedOperation]
    status: PlanStatus = PlanStatus.PENDING_APPROVAL
    parent_plan_id: str | None = None
    answer: str | None = None
    evidence: list[str] = Field(default_factory=list)
    # Raw tool results from execution, kept for the evidence view
    # (spec sections 29/50). Never included in public_view.
    results: list[dict] = Field(default_factory=list)
    error: str | None = None
    created_at: datetime = Field(default_factory=_now)
    updated_at: datetime = Field(default_factory=_now)

    def public_view(self, include_sql: bool = False) -> dict:
        """What the approval UI sees. Natural language first; SQL only on
        explicit request (spec section 16)."""
        view = {
            "plan_id": self.plan_id,
            "status": self.status.value,
            "intent": self.intent,
            "human_explanation": self.human_explanation,
            "operations": [
                {
                    "type": op.type,
                    "description": op.description,
                    "date_from": op.date_from,
                    "date_to": op.date_to,
                    "limit": op.limit,
                }
                for op in self.operations
            ],
            "created_at": self.created_at.isoformat(),
        }
        if include_sql:
            view["generated_sql"] = [op.sql for op in self.operations if op.sql]
            view["search_queries"] = [op.query for op in self.operations if op.query]
        return view
