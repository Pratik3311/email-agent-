"""Planning agent: question + history + schema → structured PlannerOutput.

Deliberate V1 topology: the planner LLM has NO tools at all. The schema it
plans against is fetched by the backend through MCP and injected as input,
and every operation it proposes goes through human approval before the
backend (not the LLM) executes it via MCP. The model is physically unable
to execute anything — the strongest possible form of "agent cannot execute
directly" (spec section 45).
"""

import json
import logging
import os
from datetime import date

from agents import Agent, Runner

from app.agent.prompts import PLANNER_INSTRUCTIONS
from app.approvals.models import PlannerOutput, QueryPlan
from app.config import get_settings
from app.mcp_client import get_company_schema

logger = logging.getLogger("agent.planner")


def _ensure_api_key() -> None:
    settings = get_settings()
    if settings.openai_api_key:
        os.environ.setdefault("OPENAI_API_KEY", settings.openai_api_key)


def _build_agent() -> Agent:
    _ensure_api_key()
    return Agent(
        name="Company Intelligence Planner",
        instructions=PLANNER_INSTRUCTIONS,
        output_type=PlannerOutput,
        model=get_settings().openai_model,
    )


def _format_history(history: list[dict]) -> str:
    if not history:
        return "(no prior conversation)"
    return "\n".join(f"{turn['role']}: {turn['content']}" for turn in history)


async def run_planner(question: str, history: list[dict]) -> PlannerOutput:
    schema = await get_company_schema()
    agent = _build_agent()
    prompt = (
        f"Current date: {date.today().isoformat()}\n\n"
        f"Database schema (the ONLY tables/columns that exist):\n"
        f"{json.dumps(schema, indent=2)}\n\n"
        f"Conversation so far:\n{_format_history(history)}\n\n"
        f"User question: {question}"
    )
    result = await Runner.run(agent, prompt)
    output: PlannerOutput = result.final_output
    logger.info("Planner status=%s intent=%s", output.status, output.intent)
    return output


async def run_replanner(old_plan: QueryPlan, instruction: str) -> PlannerOutput:
    """Regenerate a plan from a natural-language edit (spec section 18)."""
    schema = await get_company_schema()
    agent = _build_agent()
    prompt = (
        f"Current date: {date.today().isoformat()}\n\n"
        f"Database schema (the ONLY tables/columns that exist):\n"
        f"{json.dumps(schema, indent=2)}\n\n"
        f"The user previously asked: {old_plan.question}\n\n"
        f"You proposed this plan (it was NOT executed):\n"
        f"{json.dumps({'intent': old_plan.intent, 'human_explanation': old_plan.human_explanation, 'operations': [op.model_dump() for op in old_plan.operations]}, indent=2)}\n\n"
        f"The user wants this modification: {instruction}\n\n"
        f"Produce a NEW plan (status=needs_approval) incorporating the "
        f"modification, or ask for clarification if the modification is "
        f"ambiguous."
    )
    result = await Runner.run(agent, prompt)
    output: PlannerOutput = result.final_output
    logger.info("Replanner status=%s intent=%s", output.status, output.intent)
    return output
