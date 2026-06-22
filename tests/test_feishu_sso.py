import asyncio
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

import jwt
import pytest
from sqlalchemy import text
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, create_engine, select

from apps.system.api import sso as sso_api
from apps.system.crud import feishu_sso as feishu_crud
from apps.system.crud.feishu_sso import (
    FEISHU_ORIGIN,
    FeishuIdentity,
    build_feishu_authorize_url,
    create_feishu_state,
    get_feishu_sso_config,
    parse_feishu_state,
    upsert_feishu_sso_config,
)
from apps.system.crud.tenant import validate_tenant_security_policy
from apps.system.crud.user import authenticate
from apps.system.models.system_model import AuthenticationModel
from apps.system.models.tenant import TenantDomainModel, TenantModel, TenantSecurityPolicyModel, TenantUserModel
from apps.system.models.user import UserModel, UserPlatformModel
from apps.system.schemas.sso import FeishuCallbackRequest, FeishuSsoConfigEditor
from apps.system.schemas.system_schema import BaseUserDTO
from common.core.config import settings
from common.core.security import ALGORITHM, hash_password


def _engine():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TenantModel.__table__.create(engine)
    TenantUserModel.__table__.create(engine)
    TenantDomainModel.__table__.create(engine)
    TenantSecurityPolicyModel.__table__.create(engine)
    AuthenticationModel.__table__.create(engine)
    UserPlatformModel.__table__.create(engine)
    with engine.begin() as conn:
        conn.execute(text(
            """
            CREATE TABLE sys_user (
                id INTEGER PRIMARY KEY,
                account VARCHAR(255) NOT NULL UNIQUE,
                name VARCHAR(255) NOT NULL UNIQUE,
                password VARCHAR(255) NOT NULL,
                email VARCHAR(255),
                status INTEGER NOT NULL,
                origin INTEGER NOT NULL DEFAULT 0,
                create_time INTEGER NOT NULL,
                language VARCHAR(255),
                system_role VARCHAR(32) NOT NULL DEFAULT 'viewer',
                system_variables TEXT
            )
            """
        ))
    return engine


def _editor(**kwargs):
    data = {
        "enable": True,
        "app_id": "cli_test",
        "app_secret": "secret",
        "redirect_uri": "http://localhost:5173/#/login",
    }
    data.update(kwargs)
    return FeishuSsoConfigEditor(**data)


def test_feishu_config_is_optional_until_enabled_and_valid():
    engine = _engine()
    with Session(engine) as session:
        assert get_feishu_sso_config(session).enable is False
        assert build_feishu_authorize_url(session) is None

        saved = upsert_feishu_sso_config(session, _editor())
        row = session.exec(select(AuthenticationModel)).one()
        authorize_url = build_feishu_authorize_url(session, redirect="/dashboard")

        assert saved.enable is True
        assert saved.valid is True
        assert saved.secret_configured is True
        assert '"app_secret": "secret"' not in row.config
        assert authorize_url is not None
        parts = urlsplit(authorize_url)
        query = parse_qs(parts.query)
        assert parts.netloc == "open.feishu.cn"
        assert query["app_id"] == ["cli_test"]
        assert query["redirect_uri"] == ["http://localhost:5173/#/login"]
        assert query["state"][0].startswith("feishu:")


def test_feishu_state_uses_millisecond_ttl(monkeypatch):
    base_time = 100_000_000
    monkeypatch.setattr(feishu_crud, "get_timestamp", lambda: base_time)
    state = create_feishu_state()

    monkeypatch.setattr(feishu_crud, "get_timestamp", lambda: base_time + 10 * 60 * 1000 - 1)
    assert parse_feishu_state(state)["provider"] == "feishu"

    monkeypatch.setattr(feishu_crud, "get_timestamp", lambda: base_time + 10 * 60 * 1000 + 1)
    with pytest.raises(ValueError, match="expired"):
        parse_feishu_state(state)


def test_feishu_login_binds_existing_local_user_without_breaking_password_login(monkeypatch):
    engine = _engine()
    with Session(engine) as session:
        session.add(TenantModel(id=200, name="Acme", status=1, plan="basic"))
        session.add(
            TenantDomainModel(
                id=300,
                tenant_id=200,
                domain="acme.example",
                status="verified",
                auto_join_role="member",
            )
        )
        session.add(TenantSecurityPolicyModel(id=400, tenant_id=200, sso_required=True))
        session.execute(text(
            """
            INSERT INTO sys_user
                (id, account, name, password, email, status, origin, create_time, language, system_role)
            VALUES
                (10, 'alice', 'Alice', :password, 'alice@acme.example', 1, 0, 1, 'zh-CN', 'viewer')
            """
        ), {"password": hash_password("Secret123!")})
        upsert_feishu_sso_config(session, _editor())
        session.commit()

        async def fake_identity(_config, _code):
            return FeishuIdentity(
                platform_uid="ou_alice",
                open_id="ou_alice",
                email="alice@acme.example",
                name="Alice From Feishu",
            )

        monkeypatch.setattr(sso_api, "fetch_feishu_identity", fake_identity)
        state = create_feishu_state(tenant_id=200, redirect="/dashboard")
        token = asyncio.run(
            sso_api.feishu_login_callback(
                session,
                SimpleNamespace(headers={}),
                FeishuCallbackRequest(code="auth-code", state=state),
            )
        )

        payload = jwt.decode(token.access_token, settings.SECRET_KEY, algorithms=[ALGORITHM])
        stored_user = session.get(UserModel, 10)
        platform_binding = session.exec(select(UserPlatformModel).where(UserPlatformModel.uid == 10)).one()
        local_login_user = authenticate(session=session, account="alice", password="Secret123!")

        assert payload["id"] == 10
        assert payload["tenant_id"] == 200
        assert payload["auth_origin"] == FEISHU_ORIGIN
        assert token.platform_info["redirect"] == "/dashboard"
        assert stored_user.origin == 0
        assert platform_binding.origin == FEISHU_ORIGIN
        assert platform_binding.platform_uid == "ou_alice"
        assert local_login_user is not None
        assert local_login_user.origin == 0

        db_user = BaseUserDTO.model_validate(stored_user.model_dump())
        with pytest.raises(PermissionError, match="SSO"):
            validate_tenant_security_policy(session, tenant_id=200, user=db_user)

        db_user.origin = payload["auth_origin"]
        validate_tenant_security_policy(session, tenant_id=200, user=db_user)

