import os

import pytest

os.environ["LOG_FORMAT"] = "%(asctime)s - %(name)s - %(levelname)s:%(lineno)d - %(message)s"

from common.core.config import settings
from common.core.production import validate_production_settings


def _set_valid_production_settings(monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "x" * 48)
    monkeypatch.setattr(settings, "APP_ENV", "production")
    monkeypatch.setattr(settings, "PRODUCTION_CHECKS_ENABLED", True)
    monkeypatch.setattr(settings, "SECRET_KEY", "x" * 48)
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
    monkeypatch.setattr(settings, "BASE_DIR", "/opt/zhishu")
    monkeypatch.setattr(settings, "UPLOAD_DIR", "/opt/zhishu/data/file")
    monkeypatch.setattr(settings, "EXCEL_PATH", "/opt/zhishu/data/excel")
    monkeypatch.setattr(settings, "MCP_IMAGE_PATH", "/opt/zhishu/images")
    monkeypatch.setattr(settings, "LOG_DIR", "/opt/zhishu/logs")
    monkeypatch.setattr(settings, "MCP_ENABLED", False)


def test_production_settings_reject_development_defaults(monkeypatch):
    monkeypatch.delenv("SECRET_KEY", raising=False)
    monkeypatch.setattr(settings, "APP_ENV", "production")
    monkeypatch.setattr(settings, "PRODUCTION_CHECKS_ENABLED", True)
    monkeypatch.setattr(settings, "DEFAULT_PWD", "Zhishu@123456")
    monkeypatch.setattr(settings, "POSTGRES_PASSWORD", "Password123@pg")
    monkeypatch.setattr(settings, "CACHE_TYPE", "memory")
    monkeypatch.setattr(settings, "REDIS_PASSWORD", None)
    monkeypatch.setattr(settings, "REDIS_URL", None)
    monkeypatch.setattr(settings, "CACHE_REDIS_URL", None)
    monkeypatch.setattr(settings, "FRONTEND_HOST", "http://localhost:5173")
    monkeypatch.setattr(settings, "BACKEND_CORS_ORIGINS", ["http://localhost:5173"])
    monkeypatch.setattr(settings, "ENABLE_LOCAL_DEV_CORS", True)
    monkeypatch.setattr(settings, "TASK_QUEUE_MAX_ATTEMPTS", 1)
    monkeypatch.setattr(settings, "LOG_DIR", "logs")

    with pytest.raises(RuntimeError) as exc:
        validate_production_settings()

    message = str(exc.value)
    assert "SECRET_KEY must be set" in message
    assert "DEFAULT_PWD must be changed" in message
    assert "CACHE_TYPE must be redis" in message
    assert "ENABLE_LOCAL_DEV_CORS must be false" in message


def test_valid_single_tenant_production_settings_pass(monkeypatch):
    _set_valid_production_settings(monkeypatch)

    assert validate_production_settings() == []


def test_disabled_production_checks_return_errors_without_raising(monkeypatch):
    monkeypatch.delenv("SECRET_KEY", raising=False)
    monkeypatch.setattr(settings, "APP_ENV", "production")
    monkeypatch.setattr(settings, "PRODUCTION_CHECKS_ENABLED", False)
    monkeypatch.setattr(settings, "CACHE_TYPE", "memory")
    monkeypatch.setattr(settings, "DEFAULT_PWD", "Zhishu@123456")

    errors = validate_production_settings()

    assert any("CACHE_TYPE must be redis" in error for error in errors)
    assert any("DEFAULT_PWD must be changed" in error for error in errors)
