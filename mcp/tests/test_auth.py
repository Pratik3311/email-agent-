import json

import pytest

from core.auth import APIKeyMiddleware

KEY = "test-key-123"


async def dummy_app(scope, receive, send):
    await send({"type": "http.response.start", "status": 200, "headers": []})
    await send({"type": "http.response.body", "body": b"ok"})


def make_scope(headers: dict[str, str] | None = None, scope_type: str = "http") -> dict:
    return {
        "type": scope_type,
        "headers": [(k.encode(), v.encode()) for k, v in (headers or {}).items()],
    }


async def run(middleware, scope) -> tuple[int | None, bytes]:
    sent: list[dict] = []

    async def send(message):
        sent.append(message)

    async def receive():
        return {"type": "http.request"}

    await middleware(scope, receive, send)
    status = next((m["status"] for m in sent if m["type"] == "http.response.start"), None)
    body = b"".join(m.get("body", b"") for m in sent if m["type"] == "http.response.body")
    return status, body


@pytest.mark.asyncio
async def test_no_key_configured_passes_through():
    mw = APIKeyMiddleware(dummy_app, api_key="")
    status, body = await run(mw, make_scope())
    assert status == 200 and body == b"ok"


@pytest.mark.asyncio
async def test_missing_key_rejected():
    mw = APIKeyMiddleware(dummy_app, api_key=KEY)
    status, body = await run(mw, make_scope())
    assert status == 401
    assert "Unauthorized" in json.loads(body)["error"]


@pytest.mark.asyncio
async def test_wrong_key_rejected():
    mw = APIKeyMiddleware(dummy_app, api_key=KEY)
    status, _ = await run(mw, make_scope({"x-api-key": "nope"}))
    assert status == 401


@pytest.mark.asyncio
async def test_correct_key_via_header_passes():
    mw = APIKeyMiddleware(dummy_app, api_key=KEY)
    status, body = await run(mw, make_scope({"x-api-key": KEY}))
    assert status == 200 and body == b"ok"


@pytest.mark.asyncio
async def test_correct_key_via_bearer_passes():
    mw = APIKeyMiddleware(dummy_app, api_key=KEY)
    status, _ = await run(mw, make_scope({"authorization": f"Bearer {KEY}"}))
    assert status == 200


@pytest.mark.asyncio
async def test_lifespan_scope_passes_through():
    called = []

    async def lifespan_app(scope, receive, send):
        called.append(scope["type"])

    mw = APIKeyMiddleware(lifespan_app, api_key=KEY)
    await mw({"type": "lifespan"}, None, None)
    assert called == ["lifespan"]
