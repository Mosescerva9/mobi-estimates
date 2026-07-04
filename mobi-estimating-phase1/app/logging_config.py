"""Logging configuration and request-logging middleware."""

from __future__ import annotations

import json
import logging
import time
from uuid import uuid4

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.config import settings

access_logger = logging.getLogger("mobi.access")


def configure_logging() -> None:
    """Configure root logging once, based on application settings."""
    level = getattr(logging, settings.log_level.upper(), logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    logging.getLogger("mobi").setLevel(level)


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Assign a request id, time each request, and emit a structured access log.

    The request id is stored on ``request.state`` so error handlers can include
    it, and returned to the client via the ``X-Request-ID`` response header.
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        request_id = request.headers.get("X-Request-ID") or uuid4().hex
        request.state.request_id = request_id

        start = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            duration_ms = (time.perf_counter() - start) * 1000
            self._log(request, request_id, 500, duration_ms)
            raise

        duration_ms = (time.perf_counter() - start) * 1000
        response.headers["X-Request-ID"] = request_id
        self._log(request, request_id, response.status_code, duration_ms)
        return response

    @staticmethod
    def _log(request: Request, request_id: str, status_code: int, duration_ms: float) -> None:
        if settings.json_logs:
            access_logger.info(
                json.dumps(
                    {
                        "request_id": request_id,
                        "method": request.method,
                        "path": request.url.path,
                        "status_code": status_code,
                        "duration_ms": round(duration_ms, 2),
                        "client": request.client.host if request.client else None,
                    }
                )
            )
        else:
            access_logger.info(
                "%s %s -> %s (%.2fms) request_id=%s",
                request.method,
                request.url.path,
                status_code,
                duration_ms,
                request_id,
            )
