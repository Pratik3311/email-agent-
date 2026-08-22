"""The backend's ONLY road to company data: the standalone MCP server.

There are deliberately no database credentials, drivers, or SQL in this
backend. Every data operation is an MCP tool call over Streamable HTTP, so
the MCP server's validation, allowlisting, read-only enforcement, and row
caps apply to everything the backend (and therefore the agent) can do.
"""

import asyncio
import json
import logging
from typing import Any

from mcp import ClientSession
from mcp.client.streamable_http import create_mcp_http_client, streamable_http_client

from app.config import get_settings

logger = logging.getLogger("mcp_client")


def _http_client():
    """httpx client with MCP-recommended timeouts, carrying the API key the
    MCP server requires (when one is configured)."""
    settings = get_settings()
    headers = {"X-API-Key": settings.mcp_api_key} if settings.mcp_api_key else None
    return create_mcp_http_client(headers=headers)


class MCPToolError(Exception):
    """A tool call failed. Message is safe to surface to the user/agent."""


async def call_tool(name: str, arguments: dict[str, Any], timeout: float = 60.0) -> dict:
    """Call one MCP tool and return its structured result as a dict."""
    settings = get_settings()
    # Drop None arguments so optional tool params use their defaults.
    arguments = {k: v for k, v in arguments.items() if v is not None}

    try:
        async with asyncio.timeout(timeout):
            async with _http_client() as http_client:
                async with streamable_http_client(
                    settings.mcp_server_url, http_client=http_client
                ) as (read, write):
                    async with ClientSession(read, write) as session:
                        await session.initialize()
                        result = await session.call_tool(name, arguments)
    except TimeoutError:
        raise MCPToolError(f"The data service timed out on {name}.") from None
    except Exception as e:
        logger.warning("MCP call %s failed: %s: %s", name, type(e).__name__, e)
        raise MCPToolError(
            "I couldn't access the company database right now. Please try again."
        ) from None

    if result.is_error:
        text = _first_text(result)
        logger.warning("MCP tool %s returned error: %s", name, text)
        raise MCPToolError(f"The {name} operation failed: {text}")

    return _parse_result(result)


def _first_text(result: Any) -> str:
    for content in result.content or []:
        if getattr(content, "type", None) == "text":
            return content.text
    return "unknown error"


def _parse_result(result: Any) -> dict:
    structured = getattr(result, "structured_content", None)
    if isinstance(structured, dict):
        # FastMCP wraps non-object returns as {"result": ...}; unwrap dicts.
        if set(structured) == {"result"} and isinstance(structured["result"], dict):
            return structured["result"]
        return structured
    text = _first_text(result)
    try:
        parsed = json.loads(text)
        return parsed if isinstance(parsed, dict) else {"result": parsed}
    except (json.JSONDecodeError, TypeError):
        return {"result": text}


_schema_cache: dict | None = None
_schema_cached_at: float = 0.0


async def get_company_schema(force_refresh: bool = False) -> dict:
    """Fetch (and TTL-cache) the exposed schema from the MCP server. This is
    how the planner learns the database structure — via MCP, never directly.
    The MCP server discovers the schema live from the database, so schema
    changes flow through here automatically once caches expire."""
    global _schema_cache, _schema_cached_at
    settings = get_settings()
    now = asyncio.get_event_loop().time()
    stale = now - _schema_cached_at > settings.schema_cache_ttl_seconds
    if _schema_cache is None or stale or force_refresh:
        result = await call_tool("get_schema", {"refresh": force_refresh}, timeout=15.0)
        if result.get("error"):
            # Never cache a failure — surface it so the caller can respond.
            raise MCPToolError(str(result["error"]))
        _schema_cache = result
        _schema_cached_at = now
    return _schema_cache


async def check_mcp_connection() -> bool:
    settings = get_settings()
    try:
        async with asyncio.timeout(5.0):
            async with _http_client() as http_client:
                async with streamable_http_client(
                    settings.mcp_server_url, http_client=http_client
                ) as (read, write):
                    async with ClientSession(read, write) as session:
                        await session.initialize()
                        await session.list_tools()
        return True
    except Exception:
        return False
