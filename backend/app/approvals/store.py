"""In-memory plan store with locked state transitions.

The transition() method is the enforcement point for the hard invariant
"no execution without approval": execution code may only obtain a plan in
EXECUTING state by transitioning it from PENDING_APPROVAL under the lock,
so a rejected/edited/expired/already-run plan can never be executed.

In-memory is a V1 choice (plans don't survive a restart) — swap for a
Postgres/Redis-backed store later without changing the interface. Note this
would be the app's own storage, never the company clientintel database.
"""

import asyncio
from datetime import datetime, timedelta, timezone

from app.approvals.models import PlanStatus, QueryPlan


class PlanNotFoundError(Exception):
    pass


class InvalidPlanStateError(Exception):
    def __init__(self, plan_id: str, current: PlanStatus, wanted: set[PlanStatus]):
        self.current = current
        super().__init__(
            f"Plan {plan_id} is '{current.value}', expected one of "
            f"{sorted(s.value for s in wanted)}."
        )


class PlanExpiredError(Exception):
    pass


class PlanStore:
    def __init__(self, ttl_minutes: int = 30):
        self._plans: dict[str, QueryPlan] = {}
        self._lock = asyncio.Lock()
        self._ttl = timedelta(minutes=ttl_minutes)

    async def create(self, plan: QueryPlan) -> QueryPlan:
        async with self._lock:
            self._plans[plan.plan_id] = plan
            return plan

    async def get(self, plan_id: str) -> QueryPlan:
        async with self._lock:
            plan = self._plans.get(plan_id)
            if plan is None:
                raise PlanNotFoundError(f"No plan with id {plan_id}.")
            self._expire_if_stale(plan)
            return plan

    async def transition(self, plan_id: str, allowed_from: set[PlanStatus], to: PlanStatus) -> QueryPlan:
        async with self._lock:
            plan = self._plans.get(plan_id)
            if plan is None:
                raise PlanNotFoundError(f"No plan with id {plan_id}.")
            self._expire_if_stale(plan)
            if plan.status == PlanStatus.EXPIRED:
                raise PlanExpiredError(f"Plan {plan_id} has expired; ask the question again.")
            if plan.status not in allowed_from:
                raise InvalidPlanStateError(plan_id, plan.status, allowed_from)
            plan.status = to
            plan.updated_at = datetime.now(timezone.utc)
            return plan

    async def update(self, plan_id: str, **fields) -> QueryPlan:
        async with self._lock:
            plan = self._plans.get(plan_id)
            if plan is None:
                raise PlanNotFoundError(f"No plan with id {plan_id}.")
            for key, value in fields.items():
                setattr(plan, key, value)
            plan.updated_at = datetime.now(timezone.utc)
            return plan

    async def list(self, status: PlanStatus | None = None) -> list[QueryPlan]:
        async with self._lock:
            for plan in self._plans.values():
                self._expire_if_stale(plan)
            plans = list(self._plans.values())
        if status is not None:
            plans = [p for p in plans if p.status == status]
        return sorted(plans, key=lambda p: p.created_at, reverse=True)

    def _expire_if_stale(self, plan: QueryPlan) -> None:
        if plan.status == PlanStatus.PENDING_APPROVAL and (
            datetime.now(timezone.utc) - plan.created_at > self._ttl
        ):
            plan.status = PlanStatus.EXPIRED
            plan.updated_at = datetime.now(timezone.utc)
