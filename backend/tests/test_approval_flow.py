"""HITL invariants (spec section 41):
question → plan → approval → execution → answer
question → plan → rejection → NO execution
question → plan → edit → new plan → approval → execution

Uses fakes for the LLM and MCP; the workflow itself is what's under test.
"""

import pytest

from app.approvals.models import (
    AnalysisOutput,
    PlannedOperation,
    PlannerOutput,
    PlanStatus,
    QueryPlan,
)
from app.approvals.service import ApprovalService
from app.approvals.store import InvalidPlanStateError, PlanExpiredError, PlanStore
from app.audit.service import AuditService
from app.sessions import SessionStore


def make_op(**overrides) -> PlannedOperation:
    fields = {
        "type": "search_emails",
        "description": "Search rejection-related emails",
        "sql": None,
        "query": "rejected proposal",
        "date_from": "2026-08-20",
        "date_to": "2026-08-22",
        "limit": 100,
    }
    fields.update(overrides)
    return PlannedOperation(**fields)


def make_plan(**overrides) -> QueryPlan:
    fields = {
        "session_id": "s1",
        "question": "What were the rejection cases?",
        "intent": "Find rejection cases",
        "human_explanation": "I'll search emails from the last 2 days for rejections.",
        "operations": [make_op()],
    }
    fields.update(overrides)
    return QueryPlan(**fields)


class Harness:
    def __init__(self, ttl_minutes: int = 30, tmp_path=None):
        self.executed: list[tuple[str, dict]] = []
        self.store = PlanStore(ttl_minutes=ttl_minutes)
        self.audit = AuditService(log_path=str(tmp_path / "audit.log") if tmp_path else "/dev/null")
        self.sessions = SessionStore()
        self.replan_output = PlannerOutput(
            status="needs_approval",
            answer=None,
            clarification_question=None,
            intent="Find customer rejection cases",
            human_explanation="I'll search only customer-related rejection emails.",
            operations=[make_op(query="rejected proposal customer")],
        )

        async def execute(tool_name: str, args: dict) -> dict:
            self.executed.append((tool_name, args))
            return {"results": [{"email_id": 1}], "result_count": 14}

        async def analyze(question, operations, results) -> AnalysisOutput:
            return AnalysisOutput(answer="Found 14 rejection cases.", evidence=["14 matched emails"])

        async def replan(old_plan, instruction) -> PlannerOutput:
            return self.replan_output

        self.service = ApprovalService(
            store=self.store,
            audit=self.audit,
            sessions=self.sessions,
            execute_operation=execute,
            analyze=analyze,
            replan=replan,
        )


@pytest.mark.asyncio
async def test_approve_executes_and_answers(tmp_path):
    h = Harness(tmp_path=tmp_path)
    plan = await h.store.create(make_plan())

    result = await h.service.approve(plan.plan_id)

    assert result["status"] == "answer"
    assert result["answer"] == "Found 14 rejection cases."
    assert result["evidence"] == ["14 matched emails"]
    assert len(h.executed) == 1
    assert h.executed[0][0] == "search_emails"
    assert (await h.store.get(plan.plan_id)).status == PlanStatus.COMPLETED


@pytest.mark.asyncio
async def test_reject_never_executes(tmp_path):
    h = Harness(tmp_path=tmp_path)
    plan = await h.store.create(make_plan())

    result = await h.service.reject(plan.plan_id)

    assert result["status"] == "rejected"
    assert h.executed == []
    assert (await h.store.get(plan.plan_id)).status == PlanStatus.REJECTED

    # A rejected plan can never be approved afterwards.
    with pytest.raises(InvalidPlanStateError):
        await h.service.approve(plan.plan_id)
    assert h.executed == []


@pytest.mark.asyncio
async def test_edit_creates_new_pending_plan_and_never_autoexecutes(tmp_path):
    h = Harness(tmp_path=tmp_path)
    plan = await h.store.create(make_plan())

    result = await h.service.edit(plan.plan_id, "Only look at customer-related emails.")

    assert result["status"] == "awaiting_approval"
    assert h.executed == []  # editing must NOT execute anything
    assert (await h.store.get(plan.plan_id)).status == PlanStatus.EDITED

    new_plan_id = result["plan"]["plan_id"]
    assert new_plan_id != plan.plan_id
    new_plan = await h.store.get(new_plan_id)
    assert new_plan.status == PlanStatus.PENDING_APPROVAL
    assert new_plan.parent_plan_id == plan.plan_id

    # The old (edited) plan can no longer be approved.
    with pytest.raises(InvalidPlanStateError):
        await h.service.approve(plan.plan_id)

    # Approving the NEW plan executes.
    approved = await h.service.approve(new_plan_id)
    assert approved["status"] == "answer"
    assert len(h.executed) == 1


@pytest.mark.asyncio
async def test_cannot_approve_twice(tmp_path):
    h = Harness(tmp_path=tmp_path)
    plan = await h.store.create(make_plan())
    await h.service.approve(plan.plan_id)
    with pytest.raises(InvalidPlanStateError):
        await h.service.approve(plan.plan_id)
    assert len(h.executed) == 1


@pytest.mark.asyncio
async def test_expired_plan_cannot_be_approved(tmp_path):
    h = Harness(ttl_minutes=0, tmp_path=tmp_path)
    plan = await h.store.create(make_plan())
    with pytest.raises(PlanExpiredError):
        await h.service.approve(plan.plan_id)
    assert h.executed == []


@pytest.mark.asyncio
async def test_operation_error_marks_plan_failed(tmp_path):
    h = Harness(tmp_path=tmp_path)

    async def failing_execute(tool_name, args):
        return {"error": "Query rejected: Table 'import_jobs' is not authorized."}

    h.service.execute_operation = failing_execute
    plan = await h.store.create(make_plan())

    result = await h.service.approve(plan.plan_id)

    assert result["status"] == "failed"
    assert "rejected" in result["error"]
    assert (await h.store.get(plan.plan_id)).status == PlanStatus.FAILED


@pytest.mark.asyncio
async def test_missing_sql_fails_safely(tmp_path):
    h = Harness(tmp_path=tmp_path)
    plan = await h.store.create(
        make_plan(operations=[make_op(type="query_database", sql=None, query=None)])
    )
    result = await h.service.approve(plan.plan_id)
    assert result["status"] == "failed"
    assert h.executed == []
