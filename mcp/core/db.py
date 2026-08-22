import asyncpg

from core.config import get_settings

_pool: asyncpg.Pool | None = None


async def init_pool() -> asyncpg.Pool:
    """Create the shared connection pool (lazily, on first tool call).

    There is no dedicated read-only Postgres role for this database (policy
    prevents any server-side change, additive or not). Read-only is instead
    enforced entirely from this side of the connection:

    1. `default_transaction_read_only=on` — set on every connection at
       connect time. Postgres itself will refuse to run INSERT/UPDATE/
       DELETE/DROP/ALTER/etc. on any connection from this pool, independent
       of whatever privileges the underlying login actually has.
    2. Every query is additionally run inside an explicit
       `conn.transaction(readonly=True)` block (see `fetch_readonly` below)
       rather than relying on the session default alone.

    This is a real Postgres-enforced backstop, not just app code — but it is
    weaker than a dedicated role: it only protects connections made through
    this pool. Anyone connecting with the same credentials outside this app
    still has whatever privileges the underlying login has. Revisit if the
    "no server-side changes" policy ever relaxes (see db/create_readonly_role.sql).
    """
    global _pool
    if _pool is None:
        settings = get_settings()
        if not settings.database_url:
            raise RuntimeError(
                "DATABASE_URL is not configured. Create mcp/.env from mcp/.env.example "
                "and set the real connection string, then restart the MCP server."
            )
        _pool = await asyncpg.create_pool(
            dsn=settings.database_url,
            min_size=settings.db_pool_min_size,
            max_size=settings.db_pool_max_size,
            command_timeout=settings.query_timeout_seconds,
            server_settings={"default_transaction_read_only": "on"},
        )
    return _pool


async def close_pool() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


async def fetch_readonly(sql: str, *args, timeout: float | None = None) -> list[asyncpg.Record]:
    """Run a query inside an explicit read-only transaction.

    Every MCP tool that touches the database goes through this. Do not use
    pool.fetch()/conn.fetch() directly elsewhere — the explicit readonly
    transaction here is the enforcement point described in init_pool().
    """
    pool = await init_pool()
    if timeout is None:
        timeout = float(get_settings().query_timeout_seconds)
    async with pool.acquire() as conn:
        async with conn.transaction(readonly=True):
            return await conn.fetch(sql, *args, timeout=timeout)
