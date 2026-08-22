from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Read-only-in-practice connection string (see core/db.py for how
    # read-only is enforced client-side). Empty by default so the server
    # can start (and get_schema can work) before the DB is configured;
    # data tools return a clear error until it's set.
    database_url: str = ""

    mcp_host: str = "127.0.0.1"
    mcp_port: int = 8010

    # API key clients must present (X-API-Key or Bearer). Empty = auth
    # DISABLED — acceptable only for local dev on 127.0.0.1; always set it
    # when the server is reachable by anything but this machine.
    mcp_api_key: str = ""

    # Comma-separated Host header values to accept (DNS-rebinding
    # protection). Empty = SDK default, which allows localhost only — set
    # this when serving on a real host, e.g. "10.0.0.5:8010,myhost:*".
    mcp_allowed_hosts: str = ""

    db_pool_min_size: int = 1
    db_pool_max_size: int = 5

    # Defense-in-depth query limits (spec section 23). Tools must never
    # return more rows than this regardless of what a caller asks for.
    max_rows: int = 100
    query_timeout_seconds: int = 10

    # Schema exposure policy (the only database-specific configuration) and
    # how long a discovered schema snapshot stays fresh before re-reading
    # the catalogs (and the policy file) from scratch.
    schema_policy_path: str = "schema_policy.yaml"
    schema_cache_ttl_seconds: int = 300


@lru_cache
def get_settings() -> Settings:
    return Settings()
