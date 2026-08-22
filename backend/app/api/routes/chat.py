import logging

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from app.agent.planner import run_planner
from app.approvals.models import QueryPlan
from app.mcp_client import MCPToolError

logger = logging.getLogger("api.chat")

router = APIRouter()


class ChatRequest(BaseModel):
    message: str
    session_id: str | None = None


@router.post("/chat")
async def chat(req: ChatRequest, request: Request):
    """Ask a question. Returns one of:
    - {status: "answer", ...} — no data access was needed
    - {status: "needs_clarification", message}
    - {status: "awaiting_approval", plan} — approve/reject/edit via /approvals
    """
    if not req.message or not req.message.strip():
        raise HTTPException(status_code=422, detail="message must not be empty")

    sessions = request.app.state.sessions
    store = request.app.state.plan_store
    audit = request.app.state.audit

    session_id, history = sessions.get_or_create(req.session_id)

    try:
        output = await run_planner(req.message.strip(), history)
    except MCPToolError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception:
        logger.exception("Planner failed")
        raise HTTPException(
            status_code=500,
            detail="I couldn't process that question right now. Please try again.",
        )

    sessions.append(session_id, "user", req.message.strip())

    if output.status == "answer":
        answer = output.answer or "I don't have an answer for that."
        sessions.append(session_id, "assistant", answer)
        audit.log("chat_answer", session_id=session_id, question=req.message, status="answered_without_data")
        return {"status": "answer", "session_id": session_id, "answer": answer}

    if output.status == "needs_clarification":
        message = output.clarification_question or "Could you clarify what you mean?"
        sessions.append(session_id, "assistant", message)
        audit.log("chat_clarification", session_id=session_id, question=req.message)
        return {"status": "needs_clarification", "session_id": session_id, "message": message}

    # needs_approval
    if not output.operations:
        return {
            "status": "needs_clarification",
            "session_id": session_id,
            "message": "I couldn't form a concrete plan for that — could you rephrase?",
        }

    plan = QueryPlan(
        session_id=session_id,
        question=req.message.strip(),
        intent=output.intent or "",
        human_explanation=output.human_explanation or "",
        operations=output.operations,
    )
    await store.create(plan)
    audit.log(
        "plan_created",
        session_id=session_id,
        question=req.message,
        plan_id=plan.plan_id,
        generated_sql=[op.sql for op in plan.operations if op.sql],
        status="pending_approval",
    )
    sessions.append(
        session_id,
        "assistant",
        f"(Proposed a plan pending approval: {plan.human_explanation})",
    )
    return {"status": "awaiting_approval", "session_id": session_id, "plan": plan.public_view()}
