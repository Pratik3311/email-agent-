"""Run the evaluation dataset against a LIVE backend (spec section 42).

    cd backend && .venv/bin/python evals/run_evals.py [--approve] [--base URL]

Safe by default: when the agent proposes a plan, the runner records the
generated SQL/search for inspection and then REJECTS it — nothing executes.
Pass --approve to actually execute approved plans (needs the database).

Requires: backend running (and MCP + OPENAI_API_KEY for real results).
"""

import argparse
import asyncio
import json
import sys
from pathlib import Path

import httpx
import yaml


def load_cases() -> list[dict]:
    path = Path(__file__).parent / "questions.yaml"
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


async def run_case(client: httpx.AsyncClient, case: dict, approve: bool) -> dict:
    outcome = {"id": case["id"], "category": case["category"], "question": case["question"]}
    try:
        resp = await client.post("/api/chat", json={"message": case["question"]}, timeout=120)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        outcome.update(status="ERROR", passed=False, detail=f"{type(e).__name__}: {e}")
        return outcome

    status = data.get("status")
    outcome["status"] = status
    outcome["passed"] = status == case["expected_status"]

    if status == "awaiting_approval":
        plan = data.get("plan", {})
        plan_id = plan.get("plan_id")
        detail = await client.get(f"/api/approvals/{plan_id}", params={"include_sql": "true"})
        plan_full = detail.json()
        generated = " ".join(plan_full.get("generated_sql", []) + plan_full.get("search_queries", [])).lower()
        outcome["generated"] = generated
        missing = [s for s in case.get("expect_in_plan", []) if s.lower() not in generated]
        if missing:
            outcome["passed"] = False
            outcome["detail"] = f"plan missing expected substrings: {missing}"
        if approve:
            result = (await client.post(f"/api/approvals/{plan_id}/approve", timeout=300)).json()
            outcome["execution"] = result.get("status")
            outcome["answer"] = (result.get("answer") or result.get("error") or "")[:300]
        else:
            await client.post(f"/api/approvals/{plan_id}/reject")
            outcome["execution"] = "rejected (dry run)"
    elif status == "answer":
        outcome["answer"] = (data.get("answer") or "")[:300]

    return outcome


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--approve", action="store_true", help="actually execute proposed plans")
    parser.add_argument("--base", default="http://127.0.0.1:8000")
    args = parser.parse_args()

    cases = load_cases()
    results = []
    async with httpx.AsyncClient(base_url=args.base) as client:
        for case in cases:
            result = await run_case(client, case, args.approve)
            mark = "PASS" if result["passed"] else "FAIL"
            print(f"[{mark}] {result['id']:10s} {result['category']:20s} → {result.get('status')}")
            if not result["passed"] and result.get("detail"):
                print(f"       {result['detail']}")
            results.append(result)

    passed = sum(1 for r in results if r["passed"])
    print(f"\n{passed}/{len(results)} passed")

    out = Path(__file__).parent / "results.json"
    out.write_text(json.dumps(results, indent=1, ensure_ascii=False))
    print(f"Full results (including generated SQL for manual review): {out}")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
