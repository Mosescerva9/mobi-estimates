"""Structured error responses and exception handlers.

Every error returned by the API uses a single, predictable envelope::

    {
        "error": {
            "code": "not_found",
            "message": "Project not found",
            "details": null
        },
        "request_id": "..."
    }

This keeps client integrations stable regardless of which layer raised the error.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger("mobi.error")


# Map common HTTP status codes to short, stable machine-readable error codes.
# Integer literals are used for 413/422 to stay compatible across Starlette
# versions that renamed those status constants.
_STATUS_CODE_NAMES: dict[int, str] = {
    status.HTTP_400_BAD_REQUEST: "bad_request",
    status.HTTP_404_NOT_FOUND: "not_found",
    status.HTTP_409_CONFLICT: "conflict",
    413: "payload_too_large",
    status.HTTP_415_UNSUPPORTED_MEDIA_TYPE: "unsupported_media_type",
    422: "validation_error",
    status.HTTP_500_INTERNAL_SERVER_ERROR: "internal_error",
    status.HTTP_503_SERVICE_UNAVAILABLE: "service_unavailable",
}


def error_code_for_status(status_code: int) -> str:
    return _STATUS_CODE_NAMES.get(status_code, f"http_{status_code}")


def build_error_payload(
    *,
    code: str,
    message: str,
    request: Request,
    details: Any | None = None,
) -> dict[str, Any]:
    return {
        "error": {
            "code": code,
            "message": message,
            "details": details,
        },
        "request_id": getattr(request.state, "request_id", None),
    }


def _http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    payload = build_error_payload(
        code=error_code_for_status(exc.status_code),
        message=str(exc.detail),
        request=request,
    )
    return JSONResponse(
        status_code=exc.status_code,
        content=payload,
        headers=getattr(exc, "headers", None),
    )


def _validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    payload = build_error_payload(
        code="validation_error",
        message="Request validation failed",
        request=request,
        details=jsonable_encoder(exc.errors()),
    )
    return JSONResponse(
        status_code=422,
        content=payload,
    )


def _unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    # Never leak internal exception details to clients; log them server-side.
    logger.exception(
        "Unhandled exception on %s %s", request.method, request.url.path
    )
    payload = build_error_payload(
        code="internal_error",
        message="An unexpected error occurred",
        request=request,
    )
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=payload,
    )


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(StarletteHTTPException, _http_exception_handler)
    app.add_exception_handler(RequestValidationError, _validation_exception_handler)
    app.add_exception_handler(Exception, _unhandled_exception_handler)
