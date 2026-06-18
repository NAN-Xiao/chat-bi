import json

from starlette.exceptions import HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from common.core.config import settings
from common.utils.utils import AppLogUtil


def _allowed_cors_origins() -> set[str]:
    origins = {origin.rstrip("/") for origin in settings.all_cors_origins if origin}
    for instance in ResponseMiddleware.instances:
        origins.update(
            origin.rstrip("/")
            for origin in instance.allow_origins
            if origin and origin != "'self'"
        )
    return origins


def cors_headers_for_request(request: Request) -> dict[str, str]:
    origin = request.headers.get("origin")
    if not origin:
        return {}
    normalized_origin = origin.rstrip("/")
    if normalized_origin not in _allowed_cors_origins():
        return {}
    return {
        "Access-Control-Allow-Origin": normalized_origin,
        "Vary": "Origin",
    }


def _safe_http_exception_content(exc: HTTPException):
    if exc.status_code >= 500:
        return "Internal server error"
    return exc.detail


def _add_security_headers(response):
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Referrer-Policy", "same-origin")
    response.headers.setdefault("Permissions-Policy", "geolocation=(), microphone=(), camera=()")
    if settings.APP_ENV == "production":
        response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
    return response


class ResponseMiddleware(BaseHTTPMiddleware):
    instances = []

    def __init__(self, app, allow_origins: list[str] | None = None):
        super().__init__(app)
        self.allow_origins = allow_origins or ["'self'"]
        ResponseMiddleware.instances.append(self)

    def update_allow_origins(self, new_allow_origins: list[str] | None = None):
        if not new_allow_origins:
            return
        self.allow_origins = list(set(self.allow_origins + new_allow_origins))

    async def dispatch(self, request, call_next):
        response = await call_next(request)
        _add_security_headers(response)

        direct_paths = [
            f"{settings.API_V1_STR}/mcp/mcp_question",
            f"{settings.API_V1_STR}/mcp/mcp_assistant",
            f"{settings.CONTEXT_PATH}/openapi.json",
            f"{settings.CONTEXT_PATH}/docs",
            f"{settings.CONTEXT_PATH}/redoc"
        ]

        route = request.scope.get("route")
        # 获取定义的路径模式，例如 '/items/{item_id}'
        path_pattern = '' if not route else route.path_format

        if (isinstance(response, JSONResponse)
                or request.url.path == f"{settings.CONTEXT_PATH}/openapi.json"
                or path_pattern in direct_paths):
            return response
        if response.status_code != 200:
            return response
        if response.headers.get("content-type") == "application/json":
            try:
                body = b""
                async for chunk in response.body_iterator:
                    body += chunk

                raw_data = json.loads(body.decode())

                if isinstance(raw_data, dict) and all(k in raw_data for k in ["code", "data", "msg"]):
                    return JSONResponse(
                        content=raw_data,
                        status_code=response.status_code,
                        headers={
                            k: v for k, v in response.headers.items()
                            if k.lower() not in ("content-length", "content-type")
                        }
                    )

                wrapped_data = {
                    "code": 0,
                    "data": raw_data,
                    "msg": None
                }

                return JSONResponse(
                    content=wrapped_data,
                    status_code=response.status_code,
                    headers={
                        k: v for k, v in response.headers.items()
                        if k.lower() not in ("content-length", "content-type")
                    }
                )
            except Exception as e:
                AppLogUtil.error(f"Response processing error: {str(e)}", exc_info=True)
                return JSONResponse(
                    status_code=500,
                    content="Internal server error",
                    headers={
                        k: v for k, v in response.headers.items()
                        if k.lower() not in ("content-length", "content-type")
                    }
                )
        content_type = response.headers.get("content-type", "")
        static_content_types = ["text/html", "javascript", "typescript", "css"]
        if any(ct in content_type for ct in static_content_types):
            if self.allow_origins:
                frame_ancestors_value = " ".join(self.allow_origins)
                response.headers["Content-Security-Policy"] = f"frame-ancestors {frame_ancestors_value};"

        return response


class exception_handler:
    @staticmethod
    async def http_exception_handler(request: Request, exc: HTTPException):
        AppLogUtil.error(f"HTTP Exception: {exc.detail}", exc_info=True)
        return _add_security_headers(JSONResponse(
            status_code=exc.status_code,
            content=_safe_http_exception_content(exc),
            headers=cors_headers_for_request(request)
        ))

    @staticmethod
    async def global_exception_handler(request: Request, exc: Exception):
        AppLogUtil.error(f"Unhandled Exception: {str(exc)}", exc_info=True)
        return _add_security_headers(JSONResponse(
            status_code=500,
            content="Internal server error",
            headers=cors_headers_for_request(request)
        ))
