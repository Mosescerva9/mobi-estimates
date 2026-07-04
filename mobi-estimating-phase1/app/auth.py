"""Shared-secret API-key authentication middleware.

When ``settings.api_key`` is configured, every request must present the key via
either an ``X-API-Key`` header or an ``Authorization: Bearer <key>`` header.
Health probes are exempt so liveness checks and reverse-proxy health checks work
without the key. When ``settings.api_key`` is unset the middleware is a no-op,
which keeps local development and the test suite running without a key.
"""

from __future__ import annotations

import hmac

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.config import settings
from app.errors import build_error_payload

# Liveness/readiness probes must stay reachable without a key.
_EXEMPT_PATHS = frozenset(
    {
        "/health",
        "/ready",
        f"{settings.api_v1_prefix}/health",
        f"{settings.api_v1_prefix}/ready",
    }
)


def _extract_key(request: Request) -> str | None:
    header = request.headers.get("X-API-Key")
    if header:
        return header
    authorization = request.headers.get("Authorization", "")
    if authorization.lower().startswith("bearer "):
        return authorization[7:].strip()
    return None


class ApiKeyAuthMiddleware(BaseHTTPMiddleware):
    """Reject requests that lack a valid API key, when a key is configured."""

    async def dispatch(self, request: Request, call_next) -> Response:
        expected = settings.api_key
        if expected and request.url.path not in _EXEMPT_PATHS:
            provided = _extract_key(request)
            # Constant-time comparison avoids leaking the key via timing.
            if not provided or not hmac.compare_digest(provided, expected):
                payload = build_error_payload(
                    code="unauthorized",
                    message="Missing or invalid API key",
                    request=request,
                )
                return JSONResponse(status_code=401, content=payload)
        return await call_next(request)
