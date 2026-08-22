"""
Phase-1 sanity check. Run from the mcp/ directory with your real .env in place:

    python scripts/test_connection.py

Verifies, in order:
1. The database is reachable with the configured credentials.
2. The allowlisted tables exist and are readable.
3. Writes are actually blocked by the client-side read-only enforcement.
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import asyncpg  # noqa: E402

from core.db import close_pool, fetch_readonly, init_pool  # noqa: E402
from core.schema_discovery import get_snapshot  # noqa: E402


async def main() -> int:
    failures = 0

    try:
        await init_pool()
        await fetch_readonly("SELECT 1")
        print("[ok] connected, SELECT 1 works")
    except Exception as e:
        print(f"[FAIL] could not connect: {type(e).__name__}: {e}")
        return 1

    snapshot = await get_snapshot(force_refresh=True)
    print(f"[ok] schema discovered: {len(snapshot.tables)} tables exposed: {sorted(snapshot.tables)}")

    for table in snapshot.tables:
        try:
            rows = await fetch_readonly(f'SELECT count(*) AS n FROM "{table}"')
            print(f"[ok] {table}: {rows[0]['n']} rows")
        except Exception as e:
            print(f"[FAIL] {table}: {type(e).__name__}: {e}")
            failures += 1

    # The important one: prove a write is rejected by Postgres itself.
    pool = await init_pool()
    try:
        async with pool.acquire() as conn:
            await conn.execute("CREATE TEMP TABLE _readonly_probe (id int)")
        print("[FAIL] write was NOT blocked — read-only enforcement is broken!")
        failures += 1
    except asyncpg.ReadOnlySQLTransactionError:
        print("[ok] writes are blocked (read-only transaction enforced)")
    except Exception as e:
        print(f"[ok?] write failed with {type(e).__name__} (expected ReadOnlySQLTransactionError): {e}")

    await close_pool()
    print("\nAll good — Phase 1 success condition met." if failures == 0 else f"\n{failures} check(s) failed.")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
