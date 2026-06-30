import asyncio
from types import SimpleNamespace

import jwt
import pytest
from fastapi import HTTPException
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, create_engine, select
from starlette.requests import Request

from apps.system.api import apikey as apikey_api
from apps.system.middleware import auth as auth_middleware
from apps.system.models.system_model import ApiKeyModel
from apps.system.schemas.system_schema import ApikeyStatus, UserInfoDTO
from common.core import security


def _engine():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    ApiKeyModel.__table__.create(engine)
    return engine


def _user(user_id=1, tenant_id=10):
    return SimpleNamespace(id=user_id, tenant_id=tenant_id)


def _platform_admin(user_id=1, tenant_id=10):
    return SimpleNamespace(id=user_id, tenant_id=tenant_id, system_role="system_admin")


def test_api_keys_are_created_and_listed_inside_current_tenant():
    engine = _engine()
    with Session(engine) as session:
        asyncio.run(apikey_api.create.__wrapped__(session=session, current_user=_user(1, 10)))
        session.add(
            ApiKeyModel(
                id=200,
                access_key="other-tenant",
                secret_key="secret",
                create_time=1,
                uid=1,
                tenant_id=20,
                status=True,
            )
        )
        session.commit()

        row = session.exec(
            select(ApiKeyModel).where(ApiKeyModel.access_key != "other-tenant")
        ).one()
        assert row.tenant_id == 10

        visible = asyncio.run(apikey_api.grid(session=session, current_user=_user(1, 10)))
        assert [item.access_key for item in visible] == [row.access_key]


def test_platform_admin_cannot_manage_tenant_api_keys():
    engine = _engine()
    with Session(engine) as session:
        with pytest.raises(HTTPException) as exc:
            asyncio.run(apikey_api.create.__wrapped__(session=session, current_user=_platform_admin()))

        assert exc.value.status_code == 403


def test_api_key_status_and_delete_require_current_tenant():
    engine = _engine()
    with Session(engine) as session:
        api_key = ApiKeyModel(
            id=100,
            access_key="tenant-10",
            secret_key="secret",
            create_time=1,
            uid=1,
            tenant_id=10,
            status=True,
        )
        session.add(api_key)
        session.commit()

        with pytest.raises(PermissionError):
            asyncio.run(
                apikey_api.status.__wrapped__(
                    session=session,
                    current_user=_user(1, 20),
                    dto=ApikeyStatus(id=100, status=False),
                )
            )

        asyncio.run(
            apikey_api.status.__wrapped__(
                session=session,
                current_user=_user(1, 10),
                dto=ApikeyStatus(id=100, status=False),
            )
        )
        assert session.get(ApiKeyModel, 100).status is False

        with pytest.raises(PermissionError):
            asyncio.run(
                apikey_api.delete.__wrapped__(
                    session=session,
                    current_user=_user(1, 20),
                    id=100,
                )
            )

        asyncio.run(apikey_api.delete.__wrapped__(session=session, current_user=_user(1, 10), id=100))
        assert session.get(ApiKeyModel, 100) is None


def test_ask_token_cannot_override_api_key_bound_tenant(monkeypatch):
    engine = create_engine("sqlite://")
    monkeypatch.setattr(auth_middleware, "engine", engine)

    api_key = ApiKeyModel(
        id=100,
        access_key="access-1",
        secret_key="secret-1-secret-1-secret-1-secret-1",
        create_time=1,
        uid=1,
        tenant_id=10,
        status=True,
    )

    async def fake_get_api_key(_session, _access_key):
        return api_key

    async def fake_get_user_info(*, session, user_id):
        return UserInfoDTO(
            id=user_id,
            account="demo",
            name="Demo",
            email="demo@example.com",
            password="hash",
            status=1,
            origin=0,
            system_role="viewer",
        )

    monkeypatch.setattr(auth_middleware, "get_api_key", fake_get_api_key)
    monkeypatch.setattr(auth_middleware, "get_user_info", fake_get_user_info)

    token = jwt.encode(
        {"access_key": "access-1", "tenant_id": 10},
        "secret-1-secret-1-secret-1-secret-1",
        algorithm=security.ALGORITHM,
    )
    request = Request({
        "type": "http",
        "headers": [(b"x-shuzhi-tenant-id", b"20")],
    })

    middleware = auth_middleware.TokenMiddleware(app=None)
    ok, detail = asyncio.run(middleware.validateAskToken(request, f"sk {token}", auth_middleware.I18n()))

    assert ok is False
    assert detail == "Token tenant header mismatch!"
