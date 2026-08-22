"""Convert asyncpg values into JSON-safe structures for MCP tool results."""

import datetime
import decimal
import uuid
from typing import Any

import asyncpg


def to_jsonable(value: Any) -> Any:
    if isinstance(value, (datetime.datetime, datetime.date, datetime.time)):
        return value.isoformat()
    if isinstance(value, decimal.Decimal):
        return float(value)
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, (bytes, memoryview)):
        return "<binary>"
    return value


def records_to_rows(records: list[asyncpg.Record]) -> tuple[list[str], list[dict[str, Any]]]:
    if not records:
        return [], []
    columns = list(records[0].keys())
    rows = [{k: to_jsonable(v) for k, v in r.items()} for r in records]
    return columns, rows
