import logging

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel

from app.approvals.models import PlanStatus
from app.approvals.store import InvalidPlanStateError, PlanExpiredError, PlanNotFoundError

logger = logging.getLogger("api.approvals")

router = APIRouter()


class EditRequest(BaseModel):
    instruction: str


def _map_error(e: Exception) -> HTTPException:
    if isinstance(e, PlanNotFoundError):
        return HTTPException(status_code=404, detail=str(e))
    if isinstance(e, PlanExpiredError):
        return HTTPException(status_code=410, detail=str(e))
    if isinstance(e, InvalidPlanStateError):
        return HTTPException(status_code=409, detail=str(e))
    logger.exception("Approval action failed")
    return HTTPException(status_code=500, detail="Something went wrong. Please try again.")


@router.get("/approvals")
async def list_plans(request: Request, status: str | None = Query(default=None)):
    plan_status = PlanStatus(status) if status else None
    plans = await request.app.state.plan_store.list(plan_status)
    return {"plans": [p.public_view() for p in plans]}


@router.get("/approvals/{plan_id}")
async def get_plan(plan_id: str, request: Request, include_sql: bool = Query(default=False)):
    """Plan detail. Pass include_sql=true for the 'View generated SQL'
    secondary option (spec section 16)."""
    try:
        plan = await request.app.state.plan_store.get(plan_id)
    except PlanNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return plan.public_view(include_sql=include_sql)


@router.get("/approvals/{plan_id}/evidence")
async def evidence(plan_id: str, request: Request):
    """The data behind a completed answer (spec sections 29/50): the
    operations that ran (including SQL), the raw retrieved results, and the
    evidence claims. Only available once the plan completed."""
    try:
        plan = await request.app.state.plan_store.get(plan_id)
    except PlanNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    if plan.status != PlanStatus.COMPLETED:
        raise HTTPException(
            status_code=409, detail=f"Plan is '{plan.status.value}' — evidence exists only for completed plans."
        )
    return {
        "plan_id": plan.plan_id,
        "question": plan.question,
        "answer": plan.answer,
        "evidence": plan.evidence,
        "operations": [op.model_dump() for op in plan.operations],
        "results": plan.results,
    }


@router.post("/approvals/{plan_id}/approve")
async def approve(plan_id: str, request: Request):
    try:
        return await request.app.state.approvals.approve(plan_id)
    except (PlanNotFoundError, PlanExpiredError, InvalidPlanStateError) as e:
        raise _map_error(e)


@router.post("/approvals/{plan_id}/reject")
async def reject(plan_id: str, request: Request):
    try:
        return await request.app.state.approvals.reject(plan_id)
    except (PlanNotFoundError, PlanExpiredError, InvalidPlanStateError) as e:
        raise _map_error(e)


@router.post("/approvals/{plan_id}/edit")
async def edit(plan_id: str, req: EditRequest, request: Request):
    if not req.instruction or not req.instruction.strip():
        raise HTTPException(status_code=422, detail="instruction must not be empty")
    try:
        return await request.app.state.approvals.edit(plan_id, req.instruction.strip())
    except (PlanNotFoundError, PlanExpiredError, InvalidPlanStateError) as e:
        raise _map_error(e)
