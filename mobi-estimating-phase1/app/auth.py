"""Shared-secret API-key authentication middleware.

When ``settings.api_key`` is configured, every request must present exactly one
key via either an ``X-API-Key`` header or an Authorization bearer-token header.
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
from app.tenant_boundary import build_tenant_project_context

# Liveness/readiness probes must stay reachable without a key.
_EXEMPT_PATHS = frozenset(
    {
        "/health",
        "/ready",
        f"{settings.api_v1_prefix}/health",
        f"{settings.api_v1_prefix}/ready",
    }
)


def _single_header_values(request: Request, name: str) -> list[str] | None:
    """Return non-blank values for a header, or None on ambiguous coalescing."""

    values: list[str] = []
    for raw_value in request.headers.getlist(name):
        normalized = raw_value.strip()
        if not normalized:
            continue
        if "," in normalized:
            return None
        values.append(normalized)
    return values


def _extract_key(request: Request) -> str | None:
    """Extract one unambiguous shared-key credential.

    HTTP intermediaries may coalesce duplicate headers into comma-separated
    values, and Starlette preserves separately repeated headers in ``getlist``.
    Accepting either shape could let an ambiguous or smuggled auth header satisfy
    the temporary shared-key gate, so every non-health request must present
    exactly one key in exactly one supported location.
    """

    candidates = _single_header_values(request, "X-API-Key")
    authorization_headers = _single_header_values(request, "Authorization")
    if candidates is None or authorization_headers is None:
        return None
    for authorization in authorization_headers:
        if authorization.lower().startswith("bearer "):
            bearer = authorization[7:].strip()
            if not bearer or "," in bearer:
                return None
            candidates.append(bearer)
        else:
            # Unknown Authorization schemes do not count as credentials for this
            # temporary gate, but multiple/ambiguous Authorization headers still
            # fail because len(authorization_headers) will be > 1 below.
            candidates.append("")
    if len(candidates) != 1:
        return None
    return candidates[0]


def _extract_single_identity_header(request: Request, name: str) -> str | None:
    values = _single_header_values(request, name)
    if values is None or len(values) != 1:
        return None
    return values[0]


class ApiKeyAuthMiddleware(BaseHTTPMiddleware):
    """Reject requests that lack valid shared-key and tenant identity evidence.

    The shared key remains a temporary internal boundary, not the target P0 JWT /
    workload identity model. When it is enabled, require tenant/company headers on
    every non-health request so the engine cannot accept tenantless shared-key
    traffic while the stronger identity system is being built.
    """

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
            try:
                build_tenant_project_context(
                    tenant_id=_extract_single_identity_header(request, "X-Mobi-Tenant-Id"),
                    company_id=_extract_single_identity_header(request, "X-Mobi-Company-Id"),
                    # This middleware authenticates request-level tenant identity;
                    # project-specific UUID matching still belongs in route guards.
                    project_id="request-level-tenant-identity",
                )
            except PermissionError as exc:
                payload = build_error_payload(
                    code="tenant_identity_required",
                    message="Missing or invalid tenant identity headers",
                    request=request,
                    details={"reason": str(exc)},
                )
                return JSONResponse(status_code=403, content=payload)
        return await call_next(request)
