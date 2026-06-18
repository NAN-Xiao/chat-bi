import asyncio
import json
from io import BytesIO

import pytest
from fastapi import HTTPException
from starlette.datastructures import Headers, UploadFile
from starlette.requests import Request

from common.core.config import settings
from common.core.login_rate_limiter import (
    clear_login_failures,
    get_login_limit_state,
    login_limit_identity,
    record_login_failure,
    reset_memory_login_rate_limiter,
)
from common.core.response_middleware import exception_handler
from common.utils.file_utils import AppFileUtils


def _request(origin: str | None = None) -> Request:
    headers = []
    if origin:
        headers.append((b"origin", origin.encode("utf-8")))
    return Request({
        "type": "http",
        "method": "GET",
        "path": "/api/v1/demo",
        "headers": headers,
    })


def test_global_exception_handler_hides_internal_details(monkeypatch):
    monkeypatch.setattr(settings, "BACKEND_CORS_ORIGINS", ["https://bi.example.com"])
    monkeypatch.setattr(settings, "FRONTEND_HOST", "https://bi.example.com")
    monkeypatch.setattr(settings, "ENABLE_LOCAL_DEV_CORS", False)

    response = asyncio.run(
        exception_handler.global_exception_handler(
            _request("https://bi.example.com"),
            RuntimeError("database password leaked"),
        )
    )

    assert response.status_code == 500
    assert json.loads(response.body) == "Internal server error"
    assert b"database password leaked" not in response.body
    assert response.headers["Access-Control-Allow-Origin"] == "https://bi.example.com"
    assert response.headers["X-Content-Type-Options"] == "nosniff"


def test_http_500_exception_handler_hides_detail_and_rejects_unknown_origin(monkeypatch):
    monkeypatch.setattr(settings, "BACKEND_CORS_ORIGINS", ["https://bi.example.com"])
    monkeypatch.setattr(settings, "FRONTEND_HOST", "https://bi.example.com")
    monkeypatch.setattr(settings, "ENABLE_LOCAL_DEV_CORS", False)

    response = asyncio.run(
        exception_handler.http_exception_handler(
            _request("https://evil.example.com"),
            HTTPException(status_code=500, detail="raw sql failed"),
        )
    )

    assert response.status_code == 500
    assert json.loads(response.body) == "Internal server error"
    assert "Access-Control-Allow-Origin" not in response.headers


def test_safe_upload_name_strips_paths_and_requires_allowed_extension():
    base_filename, filename = AppFileUtils.safe_upload_name("../../bad.name.xlsx", {".xlsx"})

    assert "/" not in filename
    assert "\\" not in filename
    assert filename.endswith(".xlsx")
    assert base_filename.startswith("bad_name_")

    with pytest.raises(HTTPException) as exc:
        AppFileUtils.safe_upload_name("bad.exe", {".xlsx"})
    assert exc.value.status_code == 400


def test_upload_read_limit_rejects_large_file(monkeypatch):
    monkeypatch.setattr(settings, "MAX_UPLOAD_BYTES", 3)
    upload = UploadFile(
        file=BytesIO(b"toolarge"),
        filename="demo.xlsx",
        headers=Headers({"content-type": "application/octet-stream"}),
    )

    with pytest.raises(HTTPException) as exc:
        asyncio.run(AppFileUtils.read_upload_limited(upload))

    assert exc.value.status_code == 413


def test_login_rate_limiter_locks_and_clears_in_memory(monkeypatch):
    reset_memory_login_rate_limiter()
    monkeypatch.setattr(settings, "LOGIN_RATE_LIMIT_ENABLED", True)
    monkeypatch.setattr(settings, "CACHE_TYPE", "memory")
    monkeypatch.setattr(settings, "LOGIN_MAX_FAILED_ATTEMPTS", 2)
    monkeypatch.setattr(settings, "LOGIN_FAILURE_WINDOW_SECONDS", 60)
    monkeypatch.setattr(settings, "LOGIN_LOCKOUT_SECONDS", 60)

    identity = login_limit_identity("user@example.com", _request())

    assert asyncio.run(get_login_limit_state(identity)).locked is False
    assert asyncio.run(record_login_failure(identity)).locked is False
    assert asyncio.run(record_login_failure(identity)).locked is True
    assert asyncio.run(get_login_limit_state(identity)).locked is True

    asyncio.run(clear_login_failures(identity))
    assert asyncio.run(get_login_limit_state(identity)).locked is False
