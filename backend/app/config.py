from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: str = "development"

    # The backend never talks to Postgres directly — all data access goes
    # through the standalone MCP server (see ../mcp/), which it reaches as
    # an MCP client over Streamable HTTP.
    mcp_server_url: str = "http://127.0.0.1:8010/mcp"
    # Must match the MCP server's MCP_API_KEY (sent as X-API-Key).
    mcp_api_key: str = ""
    mcp_tool_timeout_seconds: float = 60.0
    # How long the planner's copy of the discovered schema stays fresh.
    schema_cache_ttl_seconds: int = 300

    openai_api_key: str = ""
    openai_model: str = "gpt-4.1"

    # Pending plans older than this can no longer be approved.
    approval_ttl_minutes: int = 30

    # Cap on retrieved-data characters injected into the analysis prompt —
    # large results are never blindly passed to the model (invariant 8).
    max_result_chars: int = 20000

    audit_log_path: str = "audit.log"


@lru_cache
def get_settings() -> Settings:
    return Settings()
