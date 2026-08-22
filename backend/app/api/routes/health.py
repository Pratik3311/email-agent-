from fastapi import APIRouter

from app.mcp_client import check_mcp_connection

router = APIRouter()


@router.get("/health")
async def health():
    mcp_ok = await check_mcp_connection()
    return {
        "status": "ok",
        "mcp_connected": mcp_ok,
        # The backend has no database connection by design — data access
        # only exists through the MCP server.
        "direct_database_access": False,
    }
