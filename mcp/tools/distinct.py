import logging

import asyncpg
from mcp.server.mcpserver import MCPServer

from core.config import get_settings
from core.db import fetch_readonly
from core.schema_discovery import get_snapshot
from core.serialize import to_jsonable

logger = logging.getLogger("mcp.get_distinct_values")


def register(server: MCPServer) -> None:
    @server.tool()
    async def get_distinct_values(table: str, column: str, limit: int = 100) -> dict:
        """List the distinct values in a column — useful for understanding
        categorical data before filtering on it.

        Only tables/columns returned by get_schema() are accepted.
        """
        try:
            snapshot = await get_snapshot()
        except RuntimeError as e:
            return {"error": str(e)}
        except Exception as e:
            logger.warning("Schema discovery failed: %s: %s", type(e).__name__, e)
            return {"error": "Could not read the database schema right now. Please try again."}

        if not snapshot.is_allowed_table(table):
            return {"error": f"Table '{table}' is not authorized. Allowed: {sorted(snapshot.tables)}."}
        if not snapshot.is_allowed_column(table, column):
            allowed = sorted(snapshot.tables[table].column_names)
            return {"error": f"Column '{column}' is not authorized on '{table}'. Allowed: {allowed}."}

        settings = get_settings()
        capped_limit = max(1, min(limit, settings.max_rows))

        # Identifiers are safe to interpolate here: both were just validated
        # by exact match against the discovered, policy-filtered schema.
        # The limit binds as a parameter.
        sql = f'SELECT DISTINCT "{column}" AS value FROM "{table}" WHERE "{column}" IS NOT NULL ORDER BY 1 LIMIT $1'

        try:
            records = await fetch_readonly(sql, capped_limit)
        except asyncpg.PostgresError as e:
            logger.warning("get_distinct_values failed: %s", e)
            return {"error": f"The lookup could not be executed: {type(e).__name__}"}
        except TimeoutError:
            return {"error": "The lookup timed out."}

        return {"values": [to_jsonable(r["value"]) for r in records]}
