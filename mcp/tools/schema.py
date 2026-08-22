import logging

from mcp.server.mcpserver import MCPServer

from core.schema_discovery import get_snapshot

logger = logging.getLogger("mcp.get_schema")


def register(server: MCPServer) -> None:
    @server.tool()
    async def get_schema(refresh: bool = False) -> dict:
        """Return the database schema available for querying: every table and
        column you are allowed to reference, with types and descriptions.
        Call this before writing SQL. Only the tables/columns returned here
        may be used in queries. Pass refresh=true if a query failed because
        the schema seems out of date."""
        try:
            snapshot = await get_snapshot(force_refresh=refresh)
        except RuntimeError as e:
            # e.g. DATABASE_URL not configured yet — clean message, no internals.
            return {"error": str(e)}
        except Exception as e:
            logger.warning("Schema discovery failed: %s: %s", type(e).__name__, e)
            return {"error": "Could not read the database schema right now. Please try again."}
        return snapshot.payload()
