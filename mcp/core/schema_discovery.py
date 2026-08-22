"""Live schema discovery.

Instead of hardcoding tables/columns, the MCP server introspects PostgreSQL's
catalogs at runtime, applies the exposure policy (schema_policy.yaml), and
caches the result with a TTL. When the database schema changes, get_schema /
query validation pick it up automatically on the next refresh — no code
changes anywhere in the stack.
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field

from core.config import get_settings
from core.db import fetch_readonly
from core.policy import SchemaPolicy, load_policy

logger = logging.getLogger("mcp.schema_discovery")

# Our own introspection query (the agent still can't touch catalogs — the
# validator rejects them; this runs inside our code on the read-only pool).
# Covers ordinary/partitioned tables, views, and materialized views.
_CATALOG_SQL = """
SELECT
    cl.relname AS table_name,
    a.attname AS column_name,
    format_type(a.atttypid, a.atttypmod) AS data_type,
    obj_description(cl.oid, 'pg_class') AS table_comment,
    col_description(cl.oid, a.attnum) AS column_comment
FROM pg_class cl
JOIN pg_namespace n ON n.oid = cl.relnamespace
JOIN pg_attribute a ON a.attrelid = cl.oid AND a.attnum > 0 AND NOT a.attisdropped
WHERE cl.relkind IN ('r', 'p', 'v', 'm')
  AND n.nspname = ANY($1::text[])
ORDER BY cl.relname, a.attnum
"""


@dataclass(frozen=True)
class ColumnInfo:
    name: str
    type: str
    description: str


@dataclass(frozen=True)
class TableInfo:
    name: str
    description: str
    columns: tuple[ColumnInfo, ...]

    @property
    def column_names(self) -> frozenset[str]:
        return frozenset(c.name for c in self.columns)


@dataclass
class SchemaSnapshot:
    tables: dict[str, TableInfo]
    fetched_at: float = field(default_factory=time.monotonic)

    def is_allowed_table(self, table: str) -> bool:
        return table in self.tables

    def is_allowed_column(self, table: str, column: str) -> bool:
        t = self.tables.get(table)
        return t is not None and column in t.column_names

    def column_types(self) -> dict[str, dict[str, str]]:
        """Shape the SQL validator consumes: {table: {column: type}}."""
        return {name: {c.name: c.type for c in t.columns} for name, t in self.tables.items()}

    def payload(self) -> dict:
        """get_schema() output (spec section 7)."""
        return {
            "tables": [
                {
                    "name": t.name,
                    "description": t.description,
                    "columns": [
                        {"name": c.name, "type": c.type, "description": c.description}
                        for c in t.columns
                    ],
                }
                for t in self.tables.values()
            ]
        }


def build_snapshot(rows: list[dict], policy: SchemaPolicy) -> SchemaSnapshot:
    """Pure function: raw catalog rows + policy → filtered snapshot."""
    grouped: dict[str, list[dict]] = {}
    for row in rows:
        grouped.setdefault(row["table_name"], []).append(row)

    tables: dict[str, TableInfo] = {}
    for table_name, cols in grouped.items():
        if policy.table_excluded(table_name):
            continue
        columns = tuple(
            ColumnInfo(
                name=c["column_name"],
                type=c["data_type"],
                description=(
                    policy.describe(table_name, c["column_name"])
                    or c.get("column_comment")
                    or ""
                ),
            )
            for c in cols
            if not policy.column_excluded(table_name, c["column_name"])
        )
        if not columns:
            # A table with every column excluded is effectively hidden.
            continue
        tables[table_name] = TableInfo(
            name=table_name,
            description=policy.describe(table_name) or cols[0].get("table_comment") or "",
            columns=columns,
        )
    return SchemaSnapshot(tables=tables)


_snapshot: SchemaSnapshot | None = None
_lock = asyncio.Lock()


async def get_snapshot(force_refresh: bool = False) -> SchemaSnapshot:
    """Return the current (policy-filtered) schema, refreshing from the
    database when stale. The policy file is re-read on every refresh, so
    policy edits also apply without a restart."""
    global _snapshot
    settings = get_settings()
    async with _lock:
        if (
            not force_refresh
            and _snapshot is not None
            and time.monotonic() - _snapshot.fetched_at < settings.schema_cache_ttl_seconds
        ):
            return _snapshot

        policy = load_policy(settings.schema_policy_path)
        rows = await fetch_readonly(_CATALOG_SQL, policy.schemas)
        _snapshot = build_snapshot([dict(r) for r in rows], policy)
        logger.info(
            "Schema discovered: %d tables exposed (%s)",
            len(_snapshot.tables),
            ", ".join(sorted(_snapshot.tables)) or "none",
        )
        return _snapshot
