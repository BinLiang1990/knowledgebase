"""Unified {code, data, msg} response envelope (docs/PRD.md §4.10).

HTTP status codes keep their real meaning (200/400/404/422/500/...); the body
is *always* the same {code, data, msg} shape regardless of status, so a caller
that only inspects the body still gets a consistent success/failure signal.
`code` inside the body is either 200 (success) or 444 (any failure), per the
PRD's own convention — it is intentionally not tied to the HTTP status line.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger("kb_backend")

CODE_OK = 200
CODE_ERROR = 444


class BusinessError(Exception):
    """Raised for expected business-rule violations (e.g. duplicate name).

    Maps to HTTP 400 by default; pass a different `status_code` for cases
    that warrant a different HTTP status while keeping the same body shape.
    """

    def __init__(self, message: str, status_code: int = status.HTTP_400_BAD_REQUEST) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def envelope(data: Any = None, msg: str = "操作成功") -> dict[str, Any]:
    return {"code": CODE_OK, "data": data if data is not None else {}, "msg": msg}


def _error_envelope(msg: str) -> dict[str, Any]:
    return {"code": CODE_ERROR, "data": {}, "msg": msg}


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(BusinessError)
    async def _business_error_handler(_: Request, exc: BusinessError) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content=_error_envelope(exc.message))

    @app.exception_handler(RequestValidationError)
    async def _validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        # The detailed field-by-field errors (names, expected types, locations)
        # are internal schema shape — don't hand them to third-party callers.
        # Log them server-side instead; the client just gets a generic message.
        # Found by the Kimi review gate on PR #17.
        logger.warning("422 validation error on %s %s: %s", request.method, request.url.path, exc.errors())
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            content=_error_envelope("请求参数校验失败"),
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http_exception_handler(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content=_error_envelope(str(exc.detail)))

    @app.exception_handler(Exception)
    async def _unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        # CTO self-review on PR #17 flagged the total absence of logging: the
        # generic 500 path swallowed the real exception, leaving nothing to
        # debug from besides the database itself. Log the full exception
        # server-side; the client still only sees "内部错误".
        logger.exception("Unhandled exception on %s %s", request.method, request.url.path, exc_info=exc)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=_error_envelope("内部错误"),
        )
