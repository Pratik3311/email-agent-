"""Schema exposure policy — the ONLY database-specific thing in this codebase,
and it's configuration, not code.

The MCP server discovers tables/columns live from PostgreSQL (see
schema_discovery.py); this policy decides what gets exposed to the agent and
how search maps onto the discovered schema. Point the server at a different
database and you edit schema_policy.yaml, never Python.
"""

import fnmatch
import logging
from pathlib import Path

import yaml
from pydantic import BaseModel, Field

logger = logging.getLogger("mcp.policy")


class SearchConfig(BaseModel):
    """Maps the generic search_emails interface onto this database's tables.
    The tool's interface (query, date range, limit → ranked snippets) never
    changes; only this mapping does."""

    table: str
    id_column: str
    date_column: str
    title_column: str
    snippet_column: str
    # Optional: a tsvector column enables indexed full-text search;
    # without it, search falls back to ILIKE over title+snippet columns.
    tsvector_column: str | None = None
    # Optional sender enrichment via a join (all four required together).
    sender_table: str | None = None
    sender_local_key: str | None = None
    sender_remote_key: str | None = None
    sender_display_column: str | None = None

    @property
    def has_sender_join(self) -> bool:
        return all(
            (self.sender_table, self.sender_local_key, self.sender_remote_key, self.sender_display_column)
        )


class SchemaPolicy(BaseModel):
    # Postgres schemas to discover tables from.
    schemas: list[str] = Field(default_factory=lambda: ["public"])
    # Table name patterns (fnmatch) to hide from the agent entirely.
    exclude_tables: list[str] = Field(default_factory=list)
    # Column name patterns applied to every table.
    exclude_column_patterns: list[str] = Field(default_factory=list)
    # Per-table column patterns: {table: [patterns]}.
    exclude_columns: dict[str, list[str]] = Field(default_factory=dict)
    # Optional human descriptions for the LLM: {"table": "...", "table.column": "..."}.
    # Postgres COMMENTs, when present, are used automatically; these override.
    descriptions: dict[str, str] = Field(default_factory=dict)
    search: SearchConfig | None = None

    def table_excluded(self, table: str) -> bool:
        t = table.lower()
        return any(fnmatch.fnmatch(t, pat.lower()) for pat in self.exclude_tables)

    def column_excluded(self, table: str, column: str) -> bool:
        c = column.lower()
        if any(fnmatch.fnmatch(c, pat.lower()) for pat in self.exclude_column_patterns):
            return True
        for tab_pat, patterns in self.exclude_columns.items():
            if fnmatch.fnmatch(table.lower(), tab_pat.lower()):
                if any(fnmatch.fnmatch(c, pat.lower()) for pat in patterns):
                    return True
        return False

    def describe(self, table: str, column: str | None = None) -> str | None:
        key = f"{table}.{column}" if column else table
        return self.descriptions.get(key)


def load_policy(path: str) -> SchemaPolicy:
    """Read the policy file. A missing file is allowed but loudly warned
    about — everything discovered would then be exposed to the agent."""
    p = Path(path)
    if not p.exists():
        logger.warning(
            "Schema policy file %s not found — ALL discovered tables/columns "
            "will be exposed to the agent. Create one to restrict exposure.",
            p.resolve(),
        )
        return SchemaPolicy()
    with p.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return SchemaPolicy(**data)
