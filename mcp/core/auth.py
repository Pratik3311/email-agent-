"""API-key authentication for the MCP server's HTTP endpoint.

Pure ASGI middleware wrapped around the SDK's Streamable HTTP app. Clients
must send the key in an `X-API-Key` header (or `Authorization: Bearer <key>`).

If no key is configured, requests pass through — acceptable only for local
development on 127.0.0.1. server.py logs a loud warning in that case, and
deployment on a reachable host must always set MCP_API_KEY.
"""

import hmac
import json


class APIKeyMiddleware:
    def __init__(self, app, api_key: str):
        self.app = app
        self.api_key = api_key

    async def __call__(self, scope, receive, send):
        # Non-HTTP scopes (lifespan) always pass through.
        if self.api_key and scope["type"] == "http":
            provided = self._extract_key(scope)
            if not provided or not hmac.compare_digest(provided, self.api_key):
                await self._reject(send)
                return
        await self.app(scope, receive, send)

    @staticmethod
    def _extract_key(scope) -> str | None:
        headers = {
            k.decode("latin-1").lower(): v.decode("latin-1")
            for k, v in scope.get("headers", [])
        }
        if key := headers.get("x-api-key"):
            return key
        auth = headers.get("authorization", "")
        if auth.lower().startswith("bearer "):
            return auth[7:].strip()
        return None

    @staticmethod
    async def _reject(send):
        body = json.dumps(
            {"error": "Unauthorized: provide the API key in an X-API-Key header."}
        ).encode()
        await send(
            {
                "type": "http.response.start",
                "status": 401,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"www-authenticate", b"Bearer"),
                    (b"content-length", str(len(body)).encode()),
                ],
            }
        )
        await send({"type": "http.response.body", "body": body})
