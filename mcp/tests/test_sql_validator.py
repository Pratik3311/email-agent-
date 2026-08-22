import pytest

from core.sql_validator import SQLValidationError, validate_and_normalize

MAX = 100

# The validator is schema-agnostic; tests feed it a schema shaped like what
# discovery produces for the clientintel database after policy filtering.
# Types are raw Postgres catalog strings on purpose (that's what it gets).
TEST_SCHEMA = {
    "clients": {
        "id": "integer",
        "email": "character varying(320)",
        "display_name": "text",
        "domain": "character varying(255)",
        "company": "character varying(255)",
        "first_seen": "timestamp with time zone",
        "last_seen": "timestamp with time zone",
    },
    "emails": {
        "id": "integer",
        "from_client_id": "integer",
        "subject": "text",
        "body_text": "text",
        "sent_date": "timestamp with time zone",
        "received_date": "timestamp with time zone",
        "has_attachment": "boolean",
        "folder": "character varying(255)",
        "thread_id": "text",
    },
    "email_participants": {
        "id": "integer",
        "email_id": "integer",
        "client_id": "integer",
        "role": "character varying(8)",
    },
    "attachments": {
        "id": "integer",
        "email_id": "integer",
        "filename": "text",
        "mime_type": "character varying(255)",
        "size": "bigint",
    },
}


def ok(sql: str) -> str:
    return validate_and_normalize(sql, MAX, TEST_SCHEMA)


def rejected(sql: str) -> str:
    with pytest.raises(SQLValidationError) as e:
        validate_and_normalize(sql, MAX, TEST_SCHEMA)
    return str(e.value)


# --- allowed ---------------------------------------------------------------


def test_simple_select_allowed():
    out = ok("SELECT subject, sent_date FROM emails")
    assert "subject" in out.lower()
    assert "limit 100" in out.lower()


def test_existing_small_limit_preserved():
    out = ok("SELECT subject FROM emails LIMIT 5")
    assert "limit 5" in out.lower()


def test_huge_limit_clamped():
    out = ok("SELECT subject FROM emails LIMIT 999999")
    assert "limit 100" in out.lower()


def test_aggregation_allowed():
    out = ok("SELECT c.email, COUNT(*) AS n FROM emails e JOIN clients c ON c.id = e.from_client_id GROUP BY c.email ORDER BY n DESC")
    assert "count" in out.lower()


def test_cte_allowed():
    out = ok(
        "WITH recent AS (SELECT id, from_client_id FROM emails WHERE sent_date >= '2026-08-20') "
        "SELECT c.email, COUNT(*) FROM recent r JOIN clients c ON c.id = r.from_client_id GROUP BY c.email"
    )
    assert "with" in out.lower()


def test_star_expands_to_allowlisted_columns_only():
    out = ok("SELECT * FROM emails").lower()
    assert "subject" in out
    # Real columns on the physical table that are NOT allowlisted must not
    # appear after star expansion.
    for hidden in ("eml_path", "body_html", "content_hash", "search_vector", "message_id", "analysis"):
        assert hidden not in out


# --- rejected: statement types ----------------------------------------------


@pytest.mark.parametrize(
    "sql",
    [
        "DELETE FROM emails",
        "INSERT INTO emails (subject) VALUES ('x')",
        "UPDATE emails SET subject = 'x'",
        "DROP TABLE emails",
        "TRUNCATE emails",
        "CREATE TABLE t (id int)",
        "ALTER TABLE emails ADD COLUMN x int",
        "GRANT SELECT ON emails TO public",
    ],
)
def test_non_select_rejected(sql):
    rejected(sql)


def test_multiple_statements_rejected():
    msg = rejected("SELECT subject FROM emails; DELETE FROM emails")
    assert "one" in msg.lower() or "multiple" in msg.lower()


def test_select_for_update_rejected():
    rejected("SELECT subject FROM emails FOR UPDATE")


# --- rejected: unauthorized tables/columns ----------------------------------


def test_unauthorized_table_rejected():
    msg = rejected("SELECT * FROM import_jobs")
    assert "import_jobs" in msg


def test_system_catalog_rejected():
    rejected("SELECT * FROM pg_catalog.pg_roles")
    rejected("SELECT rolname FROM pg_roles")
    rejected("SELECT table_name FROM information_schema.tables")


def test_schema_qualified_reference_rejected():
    rejected("SELECT subject FROM public.emails")


def test_unauthorized_column_rejected():
    rejected("SELECT eml_path FROM emails")
    rejected("SELECT body_html FROM emails")
    rejected("SELECT enrichment FROM clients")


def test_unauthorized_column_in_where_rejected():
    rejected("SELECT subject FROM emails WHERE content_hash = 'x'")


# --- rejected: dangerous functions ------------------------------------------


def test_pg_sleep_rejected():
    rejected("SELECT pg_sleep(10)")


def test_pg_read_file_rejected():
    rejected("SELECT pg_read_file('/etc/passwd')")


# --- rejected: garbage -------------------------------------------------------


def test_empty_rejected():
    rejected("")
    rejected("   ")


def test_comments_are_stripped_from_executed_sql():
    out = ok("SELECT subject /* sneaky comment */ FROM emails -- trailing")
    assert "--" not in out
    assert "/*" not in out
