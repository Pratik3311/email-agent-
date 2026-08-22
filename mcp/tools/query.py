import logging

import asyncpg
from mcp.server.mcpserver import MCPServer

from core.config import get_settings
from core.db import fetch_readonly
from core.schema_discovery import get_snapshot
from core.serialize import records_to_rows
from core.sql_validator import SQLValidationError, validate_and_normalize

logger = logging.getLogger("mcp.query_database")


def register(server: MCPServer) -> None:
    @server.tool()
    async def query_database(sql: str, max_rows: int | None = None) -> dict:
        """Execute a read-only SQL SELECT against the company database.

        Rules:
        - SELECT statements only, one statement per call.
        - Only tables/columns returned by get_schema() may be referenced.
        - Results are capped (default 100 rows) — prefer aggregation
          (COUNT/GROUP BY) over pulling raw rows when analyzing volume.
        - The query is validated and normalized before execution; the
          normalized SQL actually executed is returned as `executed_sql`.

        Returns {columns, rows, row_count, executed_sql} or {error}.
        """
        settings = get_settings()
        cap = settings.max_rows
        if max_rows is not None and 0 < max_rows < cap:
            cap = max_rows

        try:
            snapshot = await get_snapshot()
        except RuntimeError as e:
            return {"error": str(e)}
        except Exception as e:
            logger.warning("Schema discovery failed: %s: %s", type(e).__name__, e)
            return {"error": "Could not read the database schema right now. Please try again."}

        try:
            normalized = validate_and_normalize(sql, cap, snapshot.column_types())
        except SQLValidationError as e:
            logger.warning("Rejected SQL: %s | reason: %s", sql, e)
            return {"error": f"Query rejected: {e}"}

        logger.info("Executing SQL: %s", normalized)
        try:
            records = await fetch_readonly(normalized)
        except asyncpg.PostgresError as e:
            # Surface the Postgres error class/message (useful for the agent
            # to self-correct), never connection details or stack traces.
            logger.warning("Query failed: %s | %s", normalized, e)
            return {"error": f"The query could not be executed: {type(e).__name__}: {e}"}
        except TimeoutError:
            logger.warning("Query timed out: %s", normalized)
            return {"error": "The query timed out. Try a narrower filter or an aggregation."}

        columns, rows = records_to_rows(records)
        return {
            "columns": columns,
            "rows": rows,
            "row_count": len(rows),
            "executed_sql": normalized,
        }
