"""
SQL validator for query_database (spec section 22).

Schema-agnostic: the allowed tables/columns are passed in per call (built
from the live, policy-filtered schema snapshot — see schema_discovery.py),
so nothing here is tied to any particular database.

Parses SQL with sqlglot rather than string-matching, then:
- allows exactly one statement, and only a plain SELECT
- rejects SELECT INTO and locking clauses (FOR UPDATE/SHARE)
- rejects references to any table outside the allowed schema (which also
  covers pg_catalog / information_schema — they're never in it)
- resolves aliases and validates every column against the allowed schema
- expands SELECT * so only exposed columns can ever be returned
  (the physical tables may have more columns than the policy exposes —
  a raw * must not leak them)
- rejects a denylist of dangerous/infrastructure functions
- adds or clamps LIMIT so no query can return more than max_rows

The validated query is returned re-rendered from the AST, so comments and
original formatting never reach the database.
"""

import sqlglot
from sqlglot import exp
from sqlglot.errors import ParseError, SqlglotError
from sqlglot.optimizer.qualify import qualify


class SQLValidationError(Exception):
    """Raised when a query is rejected. The message is safe to show the agent
    (it never contains connection details or driver internals)."""


# Functions that probe or affect server state, filesystem, other sessions,
# or are pure denial-of-service vectors. The read-only transaction already
# blocks writes; this blocks the rest.
_BLOCKED_FUNCTIONS = frozenset(
    {
        "pg_sleep",
        "pg_sleep_for",
        "pg_sleep_until",
        "pg_read_file",
        "pg_read_binary_file",
        "pg_ls_dir",
        "pg_stat_file",
        "pg_terminate_backend",
        "pg_cancel_backend",
        "pg_reload_conf",
        "dblink",
        "dblink_exec",
        "dblink_connect",
        "lo_import",
        "lo_export",
        "set_config",
        "current_setting",
        "query_to_xml",
        "database_to_xml",
        "table_to_xml",
    }
)


def validate_and_normalize(sql: str, max_rows: int, allowed_schema: dict[str, dict[str, str]]) -> str:
    """Validate `sql` against `allowed_schema` ({table: {column: pg_type}})
    and return a normalized, LIMIT-capped version of it.

    Raises SQLValidationError on any violation.
    """
    if not sql or not sql.strip():
        raise SQLValidationError("Empty SQL statement.")
    if not allowed_schema:
        raise SQLValidationError("No tables are exposed for querying.")

    try:
        statements = [s for s in sqlglot.parse(sql, read="postgres") if s is not None]
    except ParseError as e:
        raise SQLValidationError(f"SQL could not be parsed: {e}") from None

    if len(statements) == 0:
        raise SQLValidationError("Empty SQL statement.")
    if len(statements) > 1:
        raise SQLValidationError("Exactly one SQL statement is allowed; multiple statements were found.")

    stmt = statements[0]
    if not isinstance(stmt, exp.Select):
        raise SQLValidationError("Only SELECT statements are allowed.")

    if stmt.args.get("into"):
        raise SQLValidationError("SELECT INTO is not allowed.")
    if stmt.args.get("locks"):
        raise SQLValidationError("Locking clauses (FOR UPDATE / FOR SHARE) are not allowed.")

    _check_functions(stmt)
    _check_tables(stmt, allowed_schema)

    # Resolve aliases, validate every column against the exposed schema, and
    # expand SELECT * to explicit exposed columns.
    try:
        stmt = qualify(stmt, schema=_qualify_schema(allowed_schema), dialect="postgres")
    except SqlglotError as e:
        raise SQLValidationError(f"Query references unauthorized or unknown columns: {e}") from None

    stmt = _enforce_limit(stmt, max_rows)

    # comments=False: original comments never reach the database, so they
    # can't be used to smuggle anything past downstream logging/review.
    return stmt.sql(dialect="postgres", comments=False)


def _qualify_schema(allowed_schema: dict[str, dict[str, str]]) -> dict[str, dict[str, str]]:
    """Types come straight from Postgres catalogs (e.g. 'timestamp with time
    zone', 'character varying(255)'); anything sqlglot can't parse falls back
    to TEXT — the qualifier only needs types to exist, not to be exact."""
    result: dict[str, dict[str, str]] = {}
    for table, columns in allowed_schema.items():
        cols: dict[str, str] = {}
        for name, pg_type in columns.items():
            try:
                exp.DataType.build(pg_type, dialect="postgres")
                cols[name] = pg_type.upper()
            except SqlglotError:
                cols[name] = "TEXT"
        result[table] = cols
    return result


def _check_functions(stmt: exp.Select) -> None:
    for func in stmt.find_all(exp.Func):
        if isinstance(func, exp.Anonymous):
            name = func.name
        else:
            name = func.sql_name()
        if name and name.lower() in _BLOCKED_FUNCTIONS:
            raise SQLValidationError(f"Function {name.lower()}() is not allowed.")


def _check_tables(stmt: exp.Select, allowed_schema: dict[str, dict[str, str]]) -> None:
    # CTE names look like table references when used; collect them so
    # `WITH recent AS (...) SELECT ... FROM recent` validates. The CTE
    # bodies themselves are part of the AST, so their real table
    # references are still checked below.
    cte_names = {cte.alias_or_name for cte in stmt.find_all(exp.CTE)}

    for table in stmt.find_all(exp.Table):
        if table.name in cte_names:
            continue
        if table.db or table.catalog:
            # Any schema-qualified reference (pg_catalog.x, information_schema.x,
            # public.emails, ...) is rejected outright; the exposed schema is
            # unqualified names in the application's default search path.
            raise SQLValidationError(
                f"Schema-qualified table '{table.sql()}' is not allowed. "
                f"Use unqualified allowed tables: {sorted(allowed_schema)}."
            )
        if table.name not in allowed_schema:
            raise SQLValidationError(
                f"Table '{table.name}' is not authorized. Allowed tables: {sorted(allowed_schema)}."
            )


def _enforce_limit(stmt: exp.Select, max_rows: int) -> exp.Select:
    limit_node = stmt.args.get("limit")
    if limit_node is not None:
        value = limit_node.expression
        if isinstance(value, exp.Literal) and value.is_int and int(value.this) <= max_rows:
            return stmt
    # Missing, non-literal, or too-large LIMIT → force the cap.
    return stmt.limit(max_rows)
