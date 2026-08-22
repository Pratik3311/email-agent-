"""Tests schema discovery filtering against the SHIPPED schema_policy.yaml,
so the policy file that actually deploys is what's being validated."""

from pathlib import Path

from core.policy import load_policy
from core.schema_discovery import build_snapshot

POLICY = load_policy(str(Path(__file__).resolve().parent.parent / "schema_policy.yaml"))


def row(table, column, dtype, table_comment=None, column_comment=None):
    return {
        "table_name": table,
        "column_name": column,
        "data_type": dtype,
        "table_comment": table_comment,
        "column_comment": column_comment,
    }


# Simulates what pg_catalog introspection returns for the real clientintel DB
# (including everything the policy is supposed to hide).
FAKE_CATALOG = [
    row("clients", "id", "integer"),
    row("clients", "email", "character varying(320)"),
    row("clients", "display_name", "text"),
    row("clients", "domain", "character varying(255)"),
    row("clients", "company", "character varying(255)"),
    row("clients", "first_seen", "timestamp with time zone"),
    row("clients", "last_seen", "timestamp with time zone"),
    row("clients", "enrichment", "jsonb"),
    row("clients", "created_at", "timestamp with time zone"),
    row("clients", "updated_at", "timestamp with time zone"),
    row("emails", "id", "integer"),
    row("emails", "message_id", "text"),
    row("emails", "content_hash", "character varying(64)"),
    row("emails", "from_client_id", "integer"),
    row("emails", "subject", "text"),
    row("emails", "body_text", "text"),
    row("emails", "body_html", "text"),
    row("emails", "sent_date", "timestamp with time zone"),
    row("emails", "received_date", "timestamp with time zone"),
    row("emails", "has_attachment", "boolean"),
    row("emails", "folder", "character varying(255)"),
    row("emails", "eml_path", "text"),
    row("emails", "in_reply_to", "text"),
    row("emails", "reference_ids", "text"),
    row("emails", "reply_to", "text"),
    row("emails", "thread_id", "text"),
    row("emails", "analysis", "jsonb"),
    row("emails", "search_vector", "tsvector"),
    row("emails", "created_at", "timestamp with time zone"),
    row("email_participants", "id", "integer"),
    row("email_participants", "email_id", "integer"),
    row("email_participants", "client_id", "integer"),
    row("email_participants", "role", "character varying(8)"),
    row("attachments", "id", "integer"),
    row("attachments", "email_id", "integer"),
    row("attachments", "filename", "text"),
    row("attachments", "mime_type", "character varying(255)"),
    row("attachments", "size", "bigint"),
    row("attachments", "sha256", "character varying(64)"),
    row("attachments", "storage_path", "text"),
    row("attachments", "extracted_text", "text"),
    row("import_jobs", "id", "integer"),
    row("import_jobs", "mailbox", "character varying(320)"),
    row("import_jobs", "status", "character varying(16)"),
]

SNAPSHOT = build_snapshot(FAKE_CATALOG, POLICY)


def test_import_jobs_hidden():
    assert not SNAPSHOT.is_allowed_table("import_jobs")


def test_expected_tables_exposed():
    assert set(SNAPSHOT.tables) == {"clients", "emails", "email_participants", "attachments"}


def test_sensitive_columns_hidden():
    for table, column in [
        ("emails", "eml_path"),
        ("emails", "body_html"),
        ("emails", "search_vector"),
        ("emails", "message_id"),
        ("emails", "content_hash"),
        ("emails", "analysis"),
        ("emails", "in_reply_to"),
        ("attachments", "sha256"),
        ("attachments", "storage_path"),
        ("attachments", "extracted_text"),
        ("clients", "enrichment"),
        ("clients", "created_at"),
    ]:
        assert not SNAPSHOT.is_allowed_column(table, column), f"{table}.{column} leaked"


def test_business_columns_exposed():
    for table, column in [
        ("emails", "subject"),
        ("emails", "body_text"),
        ("emails", "sent_date"),
        ("clients", "email"),
        ("clients", "company"),
        ("email_participants", "role"),
        ("attachments", "filename"),
    ]:
        assert SNAPSHOT.is_allowed_column(table, column), f"{table}.{column} missing"


def test_descriptions_applied_from_policy():
    payload = SNAPSHOT.payload()
    emails = next(t for t in payload["tables"] if t["name"] == "emails")
    assert emails["description"] == "Individual email messages."
    subject = next(c for c in emails["columns"] if c["name"] == "subject")
    assert subject["description"] == "Email subject line."


def test_pg_comment_used_when_no_policy_description():
    # email_participants.email_id has no entry in the policy's descriptions,
    # so the Postgres COMMENT should flow through.
    rows = [row("email_participants", "email_id", "integer", column_comment="A db comment")]
    snap = build_snapshot(rows, POLICY)
    col = snap.tables["email_participants"].columns[0]
    assert col.description == "A db comment"


def test_policy_description_overrides_pg_comment():
    rows = [row("emails", "subject", "text", column_comment="raw comment")]
    snap = build_snapshot(rows, POLICY)
    col = snap.tables["emails"].columns[0]
    assert col.description == "Email subject line."


def test_column_types_shape_for_validator():
    types = SNAPSHOT.column_types()
    assert types["emails"]["sent_date"] == "timestamp with time zone"
    assert "eml_path" not in types["emails"]


def test_fully_excluded_table_disappears():
    from core.policy import SchemaPolicy

    policy = SchemaPolicy(exclude_column_patterns=["*"])
    snap = build_snapshot(FAKE_CATALOG, policy)
    assert snap.tables == {}


def test_search_config_present_and_consistent():
    assert POLICY.search is not None
    assert POLICY.search.table == "emails"
    assert POLICY.search.has_sender_join


def test_search_sql_builds():
    from tools.search import build_search_sql

    sql = build_search_sql(POLICY.search)
    assert "websearch_to_tsquery" in sql
    assert '"clients"' in sql and '"emails"' in sql
    # runtime inputs are parameters, never interpolated
    for param in ("$1", "$2", "$3", "$4"):
        assert param in sql


def test_search_sql_without_tsvector_falls_back_to_ilike():
    from core.policy import SearchConfig
    from tools.search import build_search_sql

    cfg = SearchConfig(
        table="messages",
        id_column="id",
        date_column="ts",
        title_column="subj",
        snippet_column="body",
    )
    sql = build_search_sql(cfg)
    assert "websearch_to_tsquery" not in sql
    assert "ILIKE" in sql
    assert "NULL AS sender" in sql
