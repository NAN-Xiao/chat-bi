import os

import pytest
from starlette.responses import JSONResponse

os.environ["LOG_FORMAT"] = "%(asctime)s - %(name)s - %(levelname)s:%(lineno)d - %(message)s"

from common.core.config import settings
from common.core.production import validate_production_settings


def _set_valid_production_settings(monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "x" * 48)
    monkeypatch.setenv("SENSITIVE_CONFIG_ENCRYPTION_KEY", "s" * 48)
    monkeypatch.setattr(settings, "APP_ENV", "production")
    monkeypatch.setattr(settings, "PRODUCTION_CHECKS_ENABLED", True)
    monkeypatch.setattr(settings, "SECRET_KEY", "x" * 48)
    monkeypatch.setattr(settings, "SENSITIVE_CONFIG_ENCRYPTION_KEY", "s" * 48)
    monkeypatch.setattr(settings, "DATASOURCE_CONFIG_ENCRYPTION_KEY", None)
    monkeypatch.setattr(settings, "DEFAULT_PWD", "Prod-Initial-Password-Change-Me-1")
    monkeypatch.setattr(settings, "POSTGRES_PASSWORD", "Prod-Postgres-Password-Change-Me-1")
    monkeypatch.setattr(settings, "CACHE_TYPE", "redis")
    monkeypatch.setattr(settings, "REDIS_PASSWORD", "Prod-Redis-Password-Change-Me-1")
    monkeypatch.setattr(settings, "REDIS_URL", None)
    monkeypatch.setattr(settings, "CACHE_REDIS_URL", None)
    monkeypatch.setattr(settings, "FRONTEND_HOST", "https://bi.example.com")
    monkeypatch.setattr(settings, "BACKEND_CORS_ORIGINS", ["https://bi.example.com"])
    monkeypatch.setattr(settings, "ENABLE_LOCAL_DEV_CORS", False)
    monkeypatch.setattr(settings, "LOG_LEVEL", "INFO")
    monkeypatch.setattr(settings, "SQL_DEBUG", False)
    monkeypatch.setattr(settings, "ZHISHU_ALLOW_METADATA_QUERIES", False)
    monkeypatch.setattr(settings, "TASK_QUEUE_MAX_ATTEMPTS", 3)
    monkeypatch.setattr(settings, "TASK_QUEUE_VISIBILITY_TIMEOUT_SECONDS", 3600)
    monkeypatch.setattr(settings, "LOGIN_RATE_LIMIT_ENABLED", True)
    monkeypatch.setattr(settings, "LOGIN_MAX_FAILED_ATTEMPTS", 5)
    monkeypatch.setattr(settings, "LOGIN_LOCKOUT_SECONDS", 900)
    monkeypatch.setattr(settings, "MAX_UPLOAD_BYTES", 50 * 1024 * 1024)
    monkeypatch.setattr(settings, "LLM_REQUEST_TIMEOUT", 180)
    monkeypatch.setattr(settings, "SQL_QUERY_EXECUTION_TIMEOUT_SECONDS", 60)
    monkeypatch.setattr(settings, "SQL_QUERY_DEFAULT_ROW_LIMIT", 1000)
    monkeypatch.setattr(settings, "ANALYSIS_ASSISTANT_MAX_QUERIES", 4)
    monkeypatch.setattr(settings, "ANALYSIS_ASSISTANT_MAX_SQL_ROWS", 200)
    monkeypatch.setattr(settings, "CHAT_EXPORT_MAX_ROWS", 100000)
    monkeypatch.setattr(settings, "CHAT_GENERATION_CONCURRENCY_LIMIT_ENABLED", True)
    monkeypatch.setattr(settings, "CHAT_MAX_CONCURRENT_GENERATIONS_PER_USER", 1)
    monkeypatch.setattr(settings, "BASE_DIR", "/opt/zhishu")
    monkeypatch.setattr(settings, "UPLOAD_DIR", "/opt/zhishu/data/file")
    monkeypatch.setattr(settings, "EXCEL_PATH", "/opt/zhishu/data/excel")
    monkeypatch.setattr(settings, "MCP_IMAGE_PATH", "/opt/zhishu/images")
    monkeypatch.setattr(settings, "LOG_DIR", "/opt/zhishu/logs")
    monkeypatch.setattr(settings, "MCP_ENABLED", False)


def test_production_settings_reject_development_defaults(monkeypatch):
    monkeypatch.delenv("SECRET_KEY", raising=False)
    monkeypatch.delenv("SENSITIVE_CONFIG_ENCRYPTION_KEY", raising=False)
    monkeypatch.delenv("DATASOURCE_CONFIG_ENCRYPTION_KEY", raising=False)
    monkeypatch.setattr(settings, "APP_ENV", "production")
    monkeypatch.setattr(settings, "PRODUCTION_CHECKS_ENABLED", True)
    monkeypatch.setattr(settings, "SENSITIVE_CONFIG_ENCRYPTION_KEY", None)
    monkeypatch.setattr(settings, "DATASOURCE_CONFIG_ENCRYPTION_KEY", None)
    monkeypatch.setattr(settings, "DEFAULT_PWD", "elex@123")
    monkeypatch.setattr(settings, "POSTGRES_PASSWORD", "Password123@pg")
    monkeypatch.setattr(settings, "CACHE_TYPE", "memory")
    monkeypatch.setattr(settings, "REDIS_PASSWORD", None)
    monkeypatch.setattr(settings, "REDIS_URL", None)
    monkeypatch.setattr(settings, "CACHE_REDIS_URL", None)
    monkeypatch.setattr(settings, "FRONTEND_HOST", "http://localhost:5173")
    monkeypatch.setattr(settings, "BACKEND_CORS_ORIGINS", ["http://localhost:5173"])
    monkeypatch.setattr(settings, "ENABLE_LOCAL_DEV_CORS", True)
    monkeypatch.setattr(settings, "TASK_QUEUE_MAX_ATTEMPTS", 1)
    monkeypatch.setattr(settings, "LOGIN_RATE_LIMIT_ENABLED", False)
    monkeypatch.setattr(settings, "MAX_UPLOAD_BYTES", 0)
    monkeypatch.setattr(settings, "SQL_QUERY_EXECUTION_TIMEOUT_SECONDS", 0)
    monkeypatch.setattr(settings, "SQL_QUERY_DEFAULT_ROW_LIMIT", 100000)
    monkeypatch.setattr(settings, "ANALYSIS_ASSISTANT_MAX_QUERIES", 99)
    monkeypatch.setattr(settings, "CHAT_GENERATION_CONCURRENCY_LIMIT_ENABLED", False)
    monkeypatch.setattr(settings, "CHAT_MAX_CONCURRENT_GENERATIONS_PER_USER", 99)
    monkeypatch.setattr(settings, "LOG_DIR", "logs")

    with pytest.raises(RuntimeError) as exc:
        validate_production_settings()

    message = str(exc.value)
    assert "SECRET_KEY must be set" in message
    assert "SENSITIVE_CONFIG_ENCRYPTION_KEY must be set" in message
    assert "DEFAULT_PWD must be changed" in message
    assert "CACHE_TYPE must be redis" in message
    assert "ENABLE_LOCAL_DEV_CORS must be false" in message
    assert "LOGIN_RATE_LIMIT_ENABLED must be true" in message
    assert "MAX_UPLOAD_BYTES must be greater than 0" in message
    assert "SQL_QUERY_EXECUTION_TIMEOUT_SECONDS must be between 1 and 120" in message
    assert "ANALYSIS_ASSISTANT_MAX_QUERIES must be between 1 and 4" in message
    assert "CHAT_GENERATION_CONCURRENCY_LIMIT_ENABLED must be true" in message


def test_valid_single_tenant_production_settings_pass(monkeypatch):
    _set_valid_production_settings(monkeypatch)

    assert validate_production_settings() == []


def test_disabled_production_checks_return_errors_without_raising(monkeypatch):
    monkeypatch.delenv("SECRET_KEY", raising=False)
    monkeypatch.delenv("SENSITIVE_CONFIG_ENCRYPTION_KEY", raising=False)
    monkeypatch.delenv("DATASOURCE_CONFIG_ENCRYPTION_KEY", raising=False)
    monkeypatch.setattr(settings, "APP_ENV", "production")
    monkeypatch.setattr(settings, "PRODUCTION_CHECKS_ENABLED", False)
    monkeypatch.setattr(settings, "SENSITIVE_CONFIG_ENCRYPTION_KEY", None)
    monkeypatch.setattr(settings, "DATASOURCE_CONFIG_ENCRYPTION_KEY", None)
    monkeypatch.setattr(settings, "CACHE_TYPE", "memory")
    monkeypatch.setattr(settings, "DEFAULT_PWD", "elex@123")

    errors = validate_production_settings()

    assert any("CACHE_TYPE must be redis" in error for error in errors)
    assert any("DEFAULT_PWD must be changed" in error for error in errors)
    assert any("SENSITIVE_CONFIG_ENCRYPTION_KEY must be set" in error for error in errors)


def test_ready_endpoint_includes_database_cache_and_task_queue(monkeypatch):
    from main import ready
    import main as backend_main
    import asyncio
    import orjson

    monkeypatch.setattr(settings, "CACHE_TYPE", "redis")
    monkeypatch.setattr(settings, "APP_ENV", "production")
    monkeypatch.setattr(backend_main, "_database_health", lambda: {"status": "ok"})

    async def fake_cache_health():
        return {"status": "ok", "type": "redis"}

    async def fake_task_queue_health():
        return {"status": "ok", "queue": "default", "pending": 0, "processing": 0}

    monkeypatch.setattr(backend_main, "cache_health", fake_cache_health)
    monkeypatch.setattr(backend_main, "task_queue_health", fake_task_queue_health)

    response = asyncio.run(ready())

    assert isinstance(response, JSONResponse)
    assert response.status_code == 200
    payload = orjson.loads(response.body)
    assert payload["status"] == "ok"
    assert payload["database"]["status"] == "ok"
    assert payload["cache"]["status"] == "ok"
    assert payload["task_queue"]["status"] == "ok"
