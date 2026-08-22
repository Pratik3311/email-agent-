"""
Standalone MCP server — the data-access layer.

Runs as its own process, completely independent of the backend API and the
frontend. The backend connects to it as an MCP client over Streamable HTTP
at http://{MCP_HOST}:{MCP_PORT}/mcp — swap this server out (or add sibling
MCP servers for CRM/ERP later) without touching agent code.

Run:
    cd mcp
    python -m venv .venv && source .venv/bin/activate
    pip install -r requirements.txt
    cp .env.example .env   # then fill in the real DATABASE_URL
    python server.py
"""

import logging

import uvicorn
from mcp.server.mcpserver import MCPServer
from mcp.server.transport_security import TransportSecuritySettings

from core.auth import APIKeyMiddleware
from core.config import get_settings
from tools import distinct, query, record, schema, search

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")

settings = get_settings()

server = MCPServer(
    "company-intelligence-data",
    instructions=(
        "Read-only access to the company's email database. "
        "Use get_schema first to learn the structure, query_database for SQL "
        "analytics, search_emails for content search, and get_distinct_values "
        "to understand categorical columns. All access is validated and "
        "capped server-side; write operations are impossible."
    ),
)

schema.register(server)
query.register(server)
search.register(server)
distinct.register(server)
record.register(server)


def build_app():
    """The SDK's Streamable HTTP app wrapped in API-key auth."""
    transport_security = None
    if settings.mcp_allowed_hosts:
        transport_security = TransportSecuritySettings(
            allowed_hosts=[h.strip() for h in settings.mcp_allowed_hosts.split(",") if h.strip()],
        )
    app = server.streamable_http_app(
        host=settings.mcp_host,
        transport_security=transport_security,
    )
    return APIKeyMiddleware(app, settings.mcp_api_key)


if __name__ == "__main__":
    log = logging.getLogger("mcp.startup")
    log.info(
        "Starting MCP server on %s:%s — read-only enforcement is automatic on every "
        "DB connection (default_transaction_read_only=on + readonly transactions).",
        settings.mcp_host,
        settings.mcp_port,
    )
    if settings.mcp_api_key:
        log.info("API-key auth ENABLED (clients must send X-API-Key).")
    else:
        log.warning(
            "API-key auth DISABLED (MCP_API_KEY is empty). Fine for local dev on "
            "127.0.0.1 — NEVER run like this on a reachable host."
        )
    uvicorn.run(build_app(), host=settings.mcp_host, port=settings.mcp_port, log_level="info")
