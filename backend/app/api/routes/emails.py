from fastapi import APIRouter, HTTPException

from app.mcp_client import MCPToolError, call_tool

router = APIRouter()


@router.get("/emails/{email_id}")
async def get_email(email_id: int):
    """Fetch one full email (for the evidence view). Proxied through MCP —
    the backend still has no database access."""
    try:
        result = await call_tool("get_email", {"email_id": email_id}, timeout=15.0)
    except MCPToolError as e:
        raise HTTPException(status_code=503, detail=str(e))
    if result.get("error"):
        raise HTTPException(status_code=404, detail=str(result["error"]))
    return result
