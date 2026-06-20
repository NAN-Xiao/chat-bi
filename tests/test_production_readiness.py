import os
from pathlib import Path

import pytest

os.environ["LOG_FORMAT"] = "%(asctime)s - %(name)s - %(levelname)s:%(lineno)d - %(message)s"

from common.core.config import settings
from common.core.production import validate_production_settings


REPO_ROOT = Path(__file__).resolve().parents[1]


def _set_valid_production_settings(monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "x" * 48)
    monkeypatch.setenv("SENSITIVE_CONFIG_ENCRYPTION_KEY", "s" * 48)
    monkeypatch.setattr(settings, "APP_ENV", "production")
    monkeypatch.setattr(settings, "PRODUCTION_CHECKS_ENABLED", True)
    monkeypatch.setattr(settings, "AUTO_RUN_MIGRATIONS", False)
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
    monkeypatch.setattr(settings, "TENANT_RATE_LIMIT_ENABLED", True)
    monkeypatch.setattr(settings, "TENANT_CHAT_REQUESTS_PER_MINUTE", 60)
    monkeypatch.setattr(settings, "TENANT_ANALYSIS_REQUESTS_PER_MINUTE", 20)
    monkeypatch.setattr(settings, "TENANT_RECOMMEND_REQUESTS_PER_MINUTE", 30)
    monkeypatch.setattr(settings, "TENANT_LLM_REQUESTS_PER_MINUTE", 60)
    monkeypatch.setattr(settings, "TENANT_RATE_LIMIT_PLAN_OVERRIDES", "")
    monkeypatch.setattr(settings, "TENANT_USAGE_METERING_ENABLED", True)
    monkeypatch.setattr(settings, "TENANT_USAGE_QUOTA_ENABLED", True)
    monkeypatch.setattr(settings, "TENANT_USAGE_QUOTA_PLAN_LIMITS", "")
    monkeypatch.setattr(settings, "MAX_UPLOAD_BYTES", 50 * 1024 * 1024)
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
    monkeypatch.setattr(settings, "AUTO_RUN_MIGRATIONS", True)
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
    monkeypatch.setattr(settings, "TENANT_RATE_LIMIT_ENABLED", False)
    monkeypatch.setattr(settings, "TENANT_USAGE_METERING_ENABLED", False)
    monkeypatch.setattr(settings, "TENANT_USAGE_QUOTA_ENABLED", False)
    monkeypatch.setattr(settings, "TENANT_CHAT_REQUESTS_PER_MINUTE", 0)
    monkeypatch.setattr(settings, "TENANT_RATE_LIMIT_PLAN_OVERRIDES", "{bad json")
    monkeypatch.setattr(settings, "TENANT_USAGE_QUOTA_PLAN_LIMITS", "{bad json")
    monkeypatch.setattr(settings, "MAX_UPLOAD_BYTES", 0)
    monkeypatch.setattr(settings, "LOG_DIR", "logs")

    with pytest.raises(RuntimeError) as exc:
        validate_production_settings()

    message = str(exc.value)
    assert "SECRET_KEY must be set" in message
    assert "SENSITIVE_CONFIG_ENCRYPTION_KEY must be set" in message
    assert "DEFAULT_PWD must be changed" in message
    assert "CACHE_TYPE must be redis" in message
    assert "AUTO_RUN_MIGRATIONS must be false" in message
    assert "ENABLE_LOCAL_DEV_CORS must be false" in message
    assert "LOGIN_RATE_LIMIT_ENABLED must be true" in message
    assert "TENANT_RATE_LIMIT_ENABLED must be true" in message
    assert "TENANT_USAGE_METERING_ENABLED must be true" in message
    assert "TENANT_USAGE_QUOTA_ENABLED must be true" in message
    assert "TENANT_CHAT_REQUESTS_PER_MINUTE must be greater than 0" in message
    assert "TENANT_RATE_LIMIT_PLAN_OVERRIDES must be valid JSON" in message
    assert "TENANT_USAGE_QUOTA_PLAN_LIMITS must be valid JSON" in message
    assert "MAX_UPLOAD_BYTES must be greater than 0" in message


def test_valid_single_tenant_production_settings_pass(monkeypatch):
    _set_valid_production_settings(monkeypatch)

    assert validate_production_settings() == []


def test_disabled_production_checks_return_errors_without_raising(monkeypatch):
    monkeypatch.delenv("SECRET_KEY", raising=False)
    monkeypatch.delenv("SENSITIVE_CONFIG_ENCRYPTION_KEY", raising=False)
    monkeypatch.delenv("DATASOURCE_CONFIG_ENCRYPTION_KEY", raising=False)
    monkeypatch.setattr(settings, "APP_ENV", "production")
    monkeypatch.setattr(settings, "PRODUCTION_CHECKS_ENABLED", False)
    monkeypatch.setattr(settings, "AUTO_RUN_MIGRATIONS", True)
    monkeypatch.setattr(settings, "SENSITIVE_CONFIG_ENCRYPTION_KEY", None)
    monkeypatch.setattr(settings, "DATASOURCE_CONFIG_ENCRYPTION_KEY", None)
    monkeypatch.setattr(settings, "CACHE_TYPE", "memory")
    monkeypatch.setattr(settings, "DEFAULT_PWD", "elex@123")

    errors = validate_production_settings()

    assert any("CACHE_TYPE must be redis" in error for error in errors)
    assert any("AUTO_RUN_MIGRATIONS must be false" in error for error in errors)
    assert any("DEFAULT_PWD must be changed" in error for error in errors)
    assert any("SENSITIVE_CONFIG_ENCRYPTION_KEY must be set" in error for error in errors)


def test_production_postgres_backup_deployment_artifacts_are_present():
    script = (REPO_ROOT / "deploy/scripts/zhishu-postgres-backup.sh").read_text(encoding="utf-8")
    service = (REPO_ROOT / "deploy/systemd/zhishu-postgres-backup.service").read_text(encoding="utf-8")
    timer = (REPO_ROOT / "deploy/systemd/zhishu-postgres-backup.timer").read_text(encoding="utf-8")
    env_template = (REPO_ROOT / "deploy/env.production.example").read_text(encoding="utf-8")
    readiness_doc = (REPO_ROOT / "docs/single_tenant_production_readiness.md").read_text(encoding="utf-8")

    assert script.startswith("#!/usr/bin/env bash")
    assert "set -euo pipefail" in script
    assert "POSTGRES_PASSWORD" in script
    assert "--format=custom" in script
    assert "BACKUP_RETENTION_DAYS" in script
    assert "read_env_var" in script
    assert "source \"$ENV_FILE\"" not in script
    assert "sha256sum" in script or "shasum" in script
    assert "find \"$BACKUP_DIR\"" in script

    assert "EnvironmentFile=/etc/zhishu/zhishu.env" in service
    assert "ExecStart=/opt/zhishu/deploy/scripts/zhishu-postgres-backup.sh" in service
    assert "User=zhishu" in service
    assert "NoNewPrivileges=true" in service

    assert "OnCalendar=*-*-* 02:30:00" in timer
    assert "RandomizedDelaySec=1800" in timer
    assert "Persistent=true" in timer
    assert "WantedBy=timers.target" in timer

    assert "BACKUP_DIR=/var/backups/zhishu/postgres" in env_template
    assert "BACKUP_RETENTION_DAYS=14" in env_template
    assert "PG_DUMP_BIN=pg_dump" in env_template
    assert "PG_RESTORE_BIN=pg_restore" in env_template

    assert "zhishu-postgres-backup.timer" in readiness_doc
    assert "systemctl enable --now zhishu-postgres-backup.timer" in readiness_doc
    assert "自动定时备份编排" not in readiness_doc


def test_production_logrotate_deployment_artifact_is_present():
    logrotate_conf = (REPO_ROOT / "deploy/logrotate/zhishu").read_text(encoding="utf-8")
    nginx_conf = (REPO_ROOT / "deploy/nginx/nginx.production.conf.template").read_text(encoding="utf-8")
    redis_conf = (REPO_ROOT / "deploy/redis/redis.production.conf.template").read_text(encoding="utf-8")
    readiness_doc = (REPO_ROOT / "docs/single_tenant_production_readiness.md").read_text(encoding="utf-8")
    constraints_doc = (REPO_ROOT / "docs/deployment_constraints.md").read_text(encoding="utf-8")

    assert "/opt/zhishu/logs/*.log" in logrotate_conf
    assert "/var/log/nginx/zhishu.*.log" in logrotate_conf
    assert "/var/log/redis/zhishu-redis.log" in logrotate_conf
    assert "daily" in logrotate_conf
    assert "rotate 14" in logrotate_conf
    assert "maxage 30" in logrotate_conf
    assert "compress" in logrotate_conf
    assert "copytruncate" in logrotate_conf
    assert "missingok" in logrotate_conf

    assert "access_log /var/log/nginx/zhishu.access.log" in nginx_conf
    assert "error_log  /var/log/nginx/zhishu.error.log" in nginx_conf
    assert "logfile /var/log/redis/zhishu-redis.log" in redis_conf

    assert "deploy/logrotate/zhishu" in readiness_doc
    assert "logrotate -d /etc/logrotate.d/zhishu" in readiness_doc
    assert "生产日志轮转" in constraints_doc


def test_b2b_multi_tenant_architecture_direction_is_documented():
    architecture_doc = (REPO_ROOT / "docs/b2b_multi_tenant_chatbi_architecture.md").read_text(encoding="utf-8")
    readiness_doc = (REPO_ROOT / "docs/single_tenant_production_readiness.md").read_text(encoding="utf-8")
    constraints_doc = (REPO_ROOT / "docs/deployment_constraints.md").read_text(encoding="utf-8")
    env_template = (REPO_ROOT / "deploy/env.production.example").read_text(encoding="utf-8")
    redis_template = (REPO_ROOT / "deploy/redis/redis.production.conf.template").read_text(encoding="utf-8")

    assert "B2B Multi-Tenant ChatBI Architecture" in architecture_doc
    assert "sys_tenant" in architecture_doc
    assert "Smart Q&A, dashboards, custom Agents, and analysis assistant" in architecture_doc
    assert "B2B 多租户高可用生产基线" in readiness_doc
    assert "B2B 多租户高可用基线" in constraints_doc
    assert "B2B 多租户生产环境变量模板" in env_template
    assert "multi-tenant" in redis_template
    assert "不是云上多租户 SaaS" not in readiness_doc
    assert "云上多租户租户模型" not in readiness_doc


def test_production_launch_acceptance_checklist_is_documented():
    readiness_doc = (REPO_ROOT / "docs/single_tenant_production_readiness.md").read_text(encoding="utf-8")

    assert "P0 发布门禁" in readiness_doc
    assert "P0 数据与权限验收" in readiness_doc
    assert "P1 多租户商业化验收" in readiness_doc
    assert "P1 高可用与运维验收" in readiness_doc
    assert "上线前必须留存验收记录" in readiness_doc
    assert "不得从用户可达入口直接调用底层 `exec_sql`" in readiness_doc
    assert "字段权限回归" in readiness_doc
    assert "历史 ChatBI 记录、实时图表刷新、仪表盘图表、分析助手查询和 Excel 导出" in readiness_doc
    assert "quota_exceeded" in readiness_doc
    assert "worker 积压" in readiness_doc


def test_sql_execution_permission_refactor_has_no_known_dead_helper_bypasses():
    chat_crud = (REPO_ROOT / "backend/apps/chat/curd/chat.py").read_text(encoding="utf-8")
    chat_task = (REPO_ROOT / "backend/apps/chat/task/llm.py").read_text(encoding="utf-8")
    analysis_assistant = (
        REPO_ROOT / "backend/apps/analysis_assistant/api/analysis_assistant.py"
    ).read_text(encoding="utf-8")
    backend_apps_python = [
        path for path in (REPO_ROOT / "backend/apps").rglob("*.py")
        if "__pycache__" not in path.parts
    ]

    assert "def get_chart_data_ds" not in chat_crud
    assert "from apps.db.db import exec_sql" not in chat_task
    assert "from apps.db.db import exec_sql" not in analysis_assistant
    assert "exec_sql(datasource" not in analysis_assistant
    assert "apply_row_permissions=False" not in chat_task
    assert "apply_row_permissions=False" not in analysis_assistant
    for path in backend_apps_python:
        text = path.read_text(encoding="utf-8")
        assert "from apps.db.db import exec_sql" not in text
        assert "def exec_sql" not in text
        assert "def execSql" not in text


def test_low_level_sql_adapter_is_only_used_by_controlled_wrappers():
    allowed = {
        REPO_ROOT / "backend/apps/db/db.py",
        REPO_ROOT / "backend/apps/datasource/crud/query_executor.py",
        REPO_ROOT / "backend/apps/datasource/crud/datasource.py",
    }

    for path in (REPO_ROOT / "backend/apps").rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        text = path.read_text(encoding="utf-8")
        if "_unsafe_exec_sql_after_validation" in text:
            assert path in allowed
