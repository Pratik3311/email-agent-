# Company Intelligence Agent

AI-powered system for asking natural-language questions about company email
data in PostgreSQL, with mandatory human approval before any query executes.
Full spec: `data/email-project.pdf`. **Continuation context for a new
machine/session: `data/context.md`.**

## Architecture — independent processes, nothing collides

```
frontend (Next.js, :3000)  — chat + approval UI + dashboard (neo-brutalist)
    │  HTTP
    ▼
backend (FastAPI, :8000)   — agent, approvals, sessions, audit. NO database credentials.
    │  MCP over Streamable HTTP
    ▼
mcp (MCP server, :8010)    — owns ALL database access: live schema discovery,
    │                        SQL validation, read-only enforcement, 5 generic tools
    ▼
PostgreSQL (existing `clientintel` DB — never modified)
```

The database is connected ONLY to the MCP server. The backend/agent reaches
data exclusively through MCP tool calls; the agent LLM itself has no tools
and can execute nothing — it only proposes plans that humans approve.

## Running

### 0. Prereqs
```bash
# SSH tunnel to reach the database (from a machine with server2 access):
ssh -L 5433:<server3-ip>:5433 ubuntu@<server2-ip>
# Generate the shared MCP API key once:
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
```

### 1. mcp
```bash
cd mcp
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env                 # DATABASE_URL (via tunnel) + MCP_API_KEY
python scripts/test_connection.py    # verifies DB + proves writes are blocked
python server.py                     # http://127.0.0.1:8010/mcp
pytest
```
Safe by default: every DB connection automatically sets
`default_transaction_read_only=on` and every query runs in an explicit
read-only transaction — nothing manual to run when you connect the DB.
The server also starts fine before DATABASE_URL is set (data tools return a
clear error until then).

### 2. backend
```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env                 # OPENAI_API_KEY + the same MCP_API_KEY
uvicorn app.main:app --reload --port 8000
pytest                               # approval-invariant tests
```

### 3. frontend
```bash
cd frontend
npm install
cp .env.example .env.local
npm run dev                          # http://localhost:3000 (chat + dashboard)
```

### API directly (optional)
```bash
curl -s -X POST localhost:8000/api/chat -H 'content-type: application/json' \
  -d '{"message": "What were the rejection cases for the last 2 days?"}'
# → {"status":"awaiting_approval","plan":{"plan_id":"...","human_explanation":...}}

curl -s -X POST localhost:8000/api/approvals/<plan_id>/approve   # executes + answers
curl -s "localhost:8000/api/approvals/<plan_id>/evidence"        # data behind the answer
curl -s "localhost:8000/api/dashboard/overview"                  # dashboard metrics
```

### Evals (agent quality, spec section 42)
```bash
cd backend && .venv/bin/python evals/run_evals.py    # dry-run: nothing executes
```

## Schema-generic by design

Nothing about the database schema is hardcoded. The MCP server discovers
tables/columns live from PostgreSQL (cached, TTL 300s) and filters them
through `mcp/schema_policy.yaml` — the only database-specific file in the
project. Point the system at a different database (or change the schema)
and you edit that yaml (exclusions, descriptions, search mapping), never
Python. The agent learns whatever `get_schema` returns at runtime.

## Security model (V1)

- MCP endpoint requires an API key (X-API-Key header; MCP_API_KEY on both
  sides). Empty key disables auth — local dev on 127.0.0.1 only.
- Read-only enforced client-side on every MCP db connection (no server-side
  role changes are permitted on this database — see data/context.md).
- SQL parsed (sqlglot), not string-matched: single SELECT only, validated
  against the live policy-filtered schema, `SELECT *` expanded to exposed
  columns only, LIMIT forced ≤100, dangerous functions blocked, comments
  stripped.
- Hidden from the agent via schema_policy.yaml: import_jobs, file paths,
  hashes, body_html, search_vector, JSONB enrichment columns.
- No execution without explicit human approval; edited plans re-approve;
  rejected/expired plans can never run. Audit trail in backend/audit.log.
- Email content is treated as untrusted data end-to-end.

## Moving to another laptop

Copy the whole folder. `.env` files are gitignored — recreate from each
`.env.example` and re-fill real values. Recreate venvs with the commands
above. Then read `data/context.md` for full continuation context.
