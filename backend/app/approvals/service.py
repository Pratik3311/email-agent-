"""Approval workflow (spec sections 16-19, 46).

Hard invariants enforced here, outside the LLM:
- Nothing executes unless the plan transitions PENDING_APPROVAL → EXECUTING
  under the store lock (approve is the only caller of that transition).
- Reject leaves the plan terminally rejected; a later approve is impossible.
- Edit produces a NEW plan in PENDING_APPROVAL; the edited plan can never
  auto-execute.

The LLM callables (replan/analyze) and the executor are injected, so this
whole workflow is testable with fakes and independent of the agents SDK.
"""

import logging
from typing import Awaitable, Callable

from app.approvals.models import (
    AnalysisOutput,
    PlannedOperation,
    PlannerOutput,
    PlanStatus,
    QueryPlan,
)
from app.approvals.store import PlanStore
from app.audit.service import AuditService
from app.sessions import SessionStore

logger = logging.getLogger("approvals")

# (tool_name, arguments) -> tool result. The real implementation is an MCP
# tool call; tests inject a fake.
ExecuteFn = Callable[[str, dict], Awaitable[dict]]
AnalyzeFn = Callable[[str, list[PlannedOperation], list[dict]], Awaitable[AnalysisOutput]]
ReplanFn = Callable[[QueryPlan, str], Awaitable[PlannerOutput]]


class OperationError(Exception):
    pass


class ApprovalService:
    def __init__(
        self,
        store: PlanStore,
        audit: AuditService,
        sessions: SessionStore,
        execute_operation: ExecuteFn,
        analyze: AnalyzeFn,
        replan: ReplanFn,
    ):
        self.store = store
        self.audit = audit
        self.sessions = sessions
        self.execute_operation = execute_operation
        self.analyze = analyze
        self.replan = replan

    async def approve(self, plan_id: str) -> dict:
        # The one and only gate to execution.
        plan = await self.store.transition(
            plan_id, allowed_from={PlanStatus.PENDING_APPROVAL}, to=PlanStatus.EXECUTING
        )
        self.audit.log(
            "approval",
            session_id=plan.session_id,
            question=plan.question,
            plan_id=plan.plan_id,
            generated_sql=[op.sql for op in plan.operations if op.sql],
            human_action="approved",
        )

        try:
            results: list[dict] = []
            total_rows = 0
            for op in plan.operations:
                result = await self._run_operation(op)
                total_rows += int(result.get("row_count") or result.get("result_count") or 0)
                results.append(result)

            analysis = await self.analyze(plan.question, plan.operations, results)

            plan = await self.store.update(
                plan_id,
                status=PlanStatus.COMPLETED,
                answer=analysis.answer,
                evidence=analysis.evidence,
                results=results,
            )
            self.audit.log(
                "execution",
                session_id=plan.session_id,
                plan_id=plan.plan_id,
                row_count=total_rows,
                status="completed",
            )
            self.sessions.append(plan.session_id, "assistant", analysis.answer)
            return {
                "status": "answer",
                "plan_id": plan.plan_id,
                "session_id": plan.session_id,
                "answer": analysis.answer,
                "evidence": analysis.evidence,
            }
        except Exception as e:
            message = str(e) if isinstance(e, OperationError) else "Execution failed unexpectedly."
            if not isinstance(e, OperationError):
                logger.exception("Unexpected failure executing plan %s", plan_id)
            await self.store.update(plan_id, status=PlanStatus.FAILED, error=message)
            self.audit.log(
                "execution",
                session_id=plan.session_id,
                plan_id=plan_id,
                status="failed",
                error=message,
            )
            return {
                "status": "failed",
                "plan_id": plan_id,
                "session_id": plan.session_id,
                "error": f"{message} You can rephrase the question to try a different approach.",
            }

    async def reject(self, plan_id: str) -> dict:
        plan = await self.store.transition(
            plan_id, allowed_from={PlanStatus.PENDING_APPROVAL}, to=PlanStatus.REJECTED
        )
        self.audit.log(
            "approval",
            session_id=plan.session_id,
            question=plan.question,
            plan_id=plan.plan_id,
            human_action="rejected",
        )
        self.sessions.append(plan.session_id, "assistant", "(Plan was rejected by the user — nothing was executed.)")
        return {"status": "rejected", "plan_id": plan.plan_id, "session_id": plan.session_id}

    async def edit(self, plan_id: str, instruction: str) -> dict:
        # Mark the old plan first so it can never be approved concurrently
        # while the replan runs.
        old_plan = await self.store.transition(
            plan_id, allowed_from={PlanStatus.PENDING_APPROVAL}, to=PlanStatus.EDITED
        )
        self.audit.log(
            "approval",
            session_id=old_plan.session_id,
            question=old_plan.question,
            plan_id=old_plan.plan_id,
            human_action=f"edited: {instruction}",
        )

        new_output = await self.replan(old_plan, instruction)

        if new_output.status == "needs_clarification":
            return {
                "status": "needs_clarification",
                "session_id": old_plan.session_id,
                "message": new_output.clarification_question or "Could you clarify the modification?",
            }
        if new_output.status != "needs_approval" or not new_output.operations:
            return {
                "status": "error",
                "session_id": old_plan.session_id,
                "message": "I couldn't turn that modification into a new plan. Try rephrasing it.",
            }

        new_plan = QueryPlan(
            session_id=old_plan.session_id,
            question=f"{old_plan.question} (edited: {instruction})",
            intent=new_output.intent or old_plan.intent,
            human_explanation=new_output.human_explanation or "",
            operations=new_output.operations,
            parent_plan_id=old_plan.plan_id,
        )
        await self.store.create(new_plan)
        self.audit.log(
            "plan_created",
            session_id=new_plan.session_id,
            question=new_plan.question,
            plan_id=new_plan.plan_id,
            generated_sql=[op.sql for op in new_plan.operations if op.sql],
            status="pending_approval",
        )
        # The new plan requires approval again — never auto-executed.
        return {
            "status": "awaiting_approval",
            "session_id": new_plan.session_id,
            "plan": new_plan.public_view(),
        }

    async def _run_operation(self, op: PlannedOperation) -> dict:
        if op.type == "query_database":
            if not op.sql:
                raise OperationError("The plan's database operation is missing its SQL.")
            args = {"sql": op.sql, "max_rows": op.limit}
        elif op.type == "search_emails":
            if not op.query:
                raise OperationError("The plan's search operation is missing its search terms.")
            args = {
                "query": op.query,
                "date_from": op.date_from,
                "date_to": op.date_to,
                "limit": op.limit,
            }
        else:  # pragma: no cover — pydantic Literal already prevents this
            raise OperationError(f"Unknown operation type: {op.type}")

        result = await self.execute_operation(op.type, args)
        if isinstance(result, dict) and result.get("error"):
            raise OperationError(str(result["error"]))
        return result
