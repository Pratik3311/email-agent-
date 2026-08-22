"""Dashboard metrics (spec sections 30-36, phase 6).

Deliberately NOT routed through the LLM — these are fixed, hand-written
SQL queries executed via the MCP server's query_database tool, so the same
validation/caps/read-only enforcement applies, and the backend still holds
no database access. Departments are intentionally absent: the source
database has no department data, and the spec forbids inventing it.

If the schema changes, these queries fail loudly with the validator's
message rather than returning wrong numbers — surfaced as HTTP 502.
"""

import logging
import uuid

from fastapi import APIRouter, HTTPException, Query

from app.mcp_client import MCPToolError, call_tool

logger = logging.getLogger("api.dashboard")

router = APIRouter()

_ALLOWED_WINDOWS = {1, 7, 30, 90}


async def _rows(sql: str) -> list[dict]:
    try:
        result = await call_tool("query_database", {"sql": sql}, timeout=30.0)
    except MCPToolError as e:
        raise HTTPException(status_code=503, detail=str(e))
    if result.get("error"):
        logger.warning("Dashboard query failed: %s | sql: %s", result["error"], sql)
        raise HTTPException(status_code=502, detail=str(result["error"]))
    return result.get("rows", [])


async def _scalar(sql: str) -> int:
    rows = await _rows(sql)
    if not rows:
        return 0
    return int(next(iter(rows[0].values())) or 0)


@router.get("/dashboard/overview")
async def overview():
    total_emails = await _scalar("SELECT COUNT(*) AS n FROM emails")
    total_people = await _scalar("SELECT COUNT(*) AS n FROM clients")
    emails_7d = await _scalar(
        "SELECT COUNT(*) AS n FROM emails WHERE sent_date >= CURRENT_DATE - INTERVAL '7 days'"
    )
    emails_30d = await _scalar(
        "SELECT COUNT(*) AS n FROM emails WHERE sent_date >= CURRENT_DATE - INTERVAL '30 days'"
    )
    with_attachments = await _scalar(
        "SELECT COUNT(*) AS n FROM emails WHERE has_attachment = TRUE"
    )
    top_senders = await _rows(
        "SELECT c.email, c.display_name, COUNT(e.id) AS sent_count "
        "FROM emails e JOIN clients c ON c.id = e.from_client_id "
        "GROUP BY c.email, c.display_name ORDER BY sent_count DESC LIMIT 5"
    )
    top_companies = await _rows(
        "SELECT c.company, COUNT(e.id) AS email_count "
        "FROM emails e JOIN clients c ON c.id = e.from_client_id "
        "WHERE c.company IS NOT NULL AND c.company <> '' "
        "GROUP BY c.company ORDER BY email_count DESC LIMIT 5"
    )
    return {
        "total_emails": total_emails,
        "total_people": total_people,
        "emails_last_7d": emails_7d,
        "emails_last_30d": emails_30d,
        "emails_with_attachments": with_attachments,
        "top_senders": top_senders,
        "top_companies": top_companies,
    }


@router.get("/dashboard/trends")
async def trends(days: int = Query(default=30)):
    if days not in _ALLOWED_WINDOWS:
        raise HTTPException(status_code=422, detail=f"days must be one of {sorted(_ALLOWED_WINDOWS)}")
    series = await _rows(
        "SELECT DATE_TRUNC('day', sent_date) AS day, COUNT(*) AS emails "
        f"FROM emails WHERE sent_date >= CURRENT_DATE - INTERVAL '{days} days' "
        "GROUP BY 1 ORDER BY 1"
    )
    return {"days": days, "series": series}


@router.get("/dashboard/people")
async def people(limit: int = Query(default=20, ge=1, le=50)):
    sent = await _rows(
        "SELECT c.id, c.email, c.display_name, c.company, COUNT(e.id) AS sent_count, "
        "MAX(e.sent_date) AS last_email "
        "FROM clients c JOIN emails e ON e.from_client_id = c.id "
        "GROUP BY c.id, c.email, c.display_name, c.company "
        f"ORDER BY sent_count DESC LIMIT {int(limit)}"
    )
    received = await _rows(
        "SELECT c.id, COUNT(*) AS received_count "
        "FROM clients c JOIN email_participants p ON p.client_id = c.id "
        "WHERE p.role = 'to' GROUP BY c.id "
        f"ORDER BY received_count DESC LIMIT {int(limit) * 2}"
    )
    received_by_id = {r["id"]: r["received_count"] for r in received}
    for person in sent:
        person["received_count"] = received_by_id.get(person["id"], 0)
    # Transparent definition (spec section 32): "most active" = emails sent.
    return {"ranking": "by emails sent (transparent metric, not 'influence')", "people": sent}


@router.get("/dashboard/insights")
async def insights():
    """Simple computed insights (spec section 35): significant changes in
    volume and sender activity, current 7 days vs the previous 7. No
    causality claims — observed changes only."""
    current = await _scalar(
        "SELECT COUNT(*) AS n FROM emails WHERE sent_date >= CURRENT_DATE - INTERVAL '7 days'"
    )
    previous = await _scalar(
        "SELECT COUNT(*) AS n FROM emails "
        "WHERE sent_date >= CURRENT_DATE - INTERVAL '14 days' "
        "AND sent_date < CURRENT_DATE - INTERVAL '7 days'"
    )
    top_current = await _rows(
        "SELECT c.email, COUNT(*) AS n FROM emails e "
        "JOIN clients c ON c.id = e.from_client_id "
        "WHERE e.sent_date >= CURRENT_DATE - INTERVAL '7 days' "
        "GROUP BY c.email ORDER BY n DESC LIMIT 3"
    )

    items = []
    if previous > 0:
        change = round((current - previous) / previous * 100)
        if abs(change) >= 20:
            direction = "increased" if change > 0 else "decreased"
            items.append(
                {
                    "id": str(uuid.uuid4()),
                    "type": "trend",
                    "title": f"Email volume {direction} {abs(change)}% week-over-week",
                    "description": f"{current} emails in the last 7 days vs {previous} in the 7 days before.",
                    "severity": "high" if abs(change) >= 50 else "medium",
                    "metric": {"current": current, "baseline": previous, "change_percent": change},
                    "confidence": 0.9,
                }
            )
    elif current > 0:
        items.append(
            {
                "id": str(uuid.uuid4()),
                "type": "trend",
                "title": "Email activity started this week",
                "description": f"{current} emails in the last 7 days after none in the prior week.",
                "severity": "low",
                "metric": {"current": current, "baseline": 0, "change_percent": None},
                "confidence": 0.9,
            }
        )
    for sender in top_current:
        items.append(
            {
                "id": str(uuid.uuid4()),
                "type": "activity",
                "title": f"Most active sender this week: {sender['email']}",
                "description": f"{sender['n']} emails sent in the last 7 days.",
                "severity": "low",
                "metric": {"current": sender["n"], "baseline": None, "change_percent": None},
                "confidence": 1.0,
            }
        )
        break  # only the top one as an insight; the rest live in /people
    return {"insights": items}
