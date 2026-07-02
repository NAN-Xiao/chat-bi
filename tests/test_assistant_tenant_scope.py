import asyncio
import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import jwt
import pytest
from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, create_engine
from starlette.requests import Request
from starlette.responses import Response

from apps.system.api import assistant as assistant_api
from apps.system.models.system_model import AssistantModel
from apps.system.schemas.system_schema import AssistantBase, AssistantDTO, AssistantHeader
from common.core import security
from common.core.config import settings


def _engine():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    AssistantModel.__table__.create(engine)
    with engine.begin() as conn:
        conn.execute(text(
            """
            CREATE TABLE core_datasource (
                id INTEGER PRIMARY KEY,
                tenant_id INTEGER NOT NULL DEFAULT 1,
                name VARCHAR(128) NOT NULL,
                description VARCHAR(512),
                type VARCHAR(64),
                type_name VARCHAR(64),
                num VARCHAR(256)
            )
            """
        ))
    return engine


def _unwrap(func):
    while hasattr(func, "__wrapped__"):
        func = func.__wrapped__
    return func


def _request():
    return SimpleNamespace(app=SimpleNamespace(user_middleware=[]))


def _http_request(*, origin: str = "https://example.com", credential: str | None = None):
    headers = [(b"x-shuzhi-host-origin", origin.encode("utf-8"))]
    if credential:
        headers.append((b"x-shuzhi-assistant-validator", f"Embedded {credential}".encode("utf-8")))
    return Request({"type": "http", "method": "GET", "path": "/system/assistant/validator", "headers": headers})


def _trans(key: str, **kwargs):
    return key.format(**kwargs) if kwargs else key


def _validator_credential(assistant: AssistantModel, *, origin: str = "https://example.com") -> str:
    return jwt.encode(
        {
            "assistant_id": assistant.id,
            "tenant_id": assistant.tenant_id,
            "origin": origin,
            "exp": datetime.now(timezone.utc) + timedelta(minutes=5),
        },
        assistant.app_secret,
        algorithm=security.ALGORITHM,
    )


def _tenant_admin(tenant_id=10):
    return SimpleNamespace(
        id=2,
        system_role="viewer",
        tenant_id=tenant_id,
        tenant_role="admin",
    )


def _platform_admin():
    return SimpleNamespace(
        id=1,
        system_role="system_admin",
        tenant_id=10,
        tenant_role="owner",
    )


def _assistant(assistant_id: int, tenant_id: int, name: str, type_: int = 0) -> AssistantModel:
    return AssistantModel(
        id=assistant_id,
        tenant_id=tenant_id,
        name=name,
        type=type_,
        domain="https://example.com",
        description="demo",
        configuration=json.dumps({"public_list": [101, 201]}),
        create_time=assistant_id,
        app_id=f"app-{assistant_id}",
        app_secret=f"secret-{assistant_id}",
        enable_custom_model=False,
        custom_model="",
    )


def _assistant_base(name="Tenant Assistant") -> AssistantBase:
    return AssistantBase(
        name=name,
        type=0,
        domain="https://example.com",
        description="demo",
        configuration=json.dumps({"public_list": []}),
        enable_custom_model=False,
        custom_model=None,
    )


def _assistant_editor(assistant_id: int, name="Updated Assistant") -> AssistantDTO:
    return AssistantDTO(
        id=assistant_id,
        name=name,
        type=0,
        domain="https://example.com",
        description="updated",
        configuration=json.dumps({"public_list": []}),
        enable_custom_model=False,
        custom_model=None,
    )


def test_tenant_admin_lists_only_current_tenant_assistants():
    engine = _engine()
    with Session(engine) as session:
        session.add(_assistant(101, 10, "Tenant A"))
        session.add(_assistant(201, 20, "Tenant B"))
        session.commit()

        visible = asyncio.run(
            _unwrap(assistant_api.query)(session=session, current_user=_tenant_admin(10))
        )
        all_visible = asyncio.run(
            _unwrap(assistant_api.query)(session=session, current_user=_platform_admin())
        )

        assert [item.id for item in visible] == [101]
        assert {item.id for item in all_visible} == {101, 201}


def test_assistant_create_sets_current_tenant():
    engine = _engine()
    with Session(engine) as session:
        created = asyncio.run(
            _unwrap(assistant_api.add)(
                request=_request(),
                session=session,
                current_user=_tenant_admin(10),
                creator=_assistant_base(),
            )
        )

        assert created.tenant_id == 10
        assert session.get(AssistantModel, created.id).tenant_id == 10


def test_tenant_admin_cannot_update_or_delete_other_tenant_assistant():
    engine = _engine()
    with Session(engine) as session:
        session.add(_assistant(201, 20, "Tenant B"))
        session.commit()

        with pytest.raises(HTTPException) as update_exc:
            asyncio.run(
                _unwrap(assistant_api.update)(
                    request=_request(),
                    session=session,
                    current_user=_tenant_admin(10),
                    editor=_assistant_editor(201),
                )
            )
        assert update_exc.value.status_code == 404

        with pytest.raises(HTTPException) as delete_exc:
            asyncio.run(
                _unwrap(assistant_api.delete)(
                    request=_request(),
                    session=session,
                    current_user=_tenant_admin(10),
                    id=201,
                )
            )
        assert delete_exc.value.status_code == 404
        assert session.get(AssistantModel, 201) is not None


def test_assistant_update_preserves_tenant_id():
    engine = _engine()
    with Session(engine) as session:
        session.add(_assistant(101, 10, "Tenant A"))
        session.commit()

        asyncio.run(
            _unwrap(assistant_api.update)(
                request=_request(),
                session=session,
                current_user=_tenant_admin(10),
                editor=_assistant_editor(101),
            )
        )

        updated = session.get(AssistantModel, 101)
        assert updated.name == "Updated Assistant"
        assert updated.tenant_id == 10


def test_assistant_ds_is_filtered_by_assistant_tenant():
    engine = _engine()
    with Session(engine) as session:
        session.exec(text(
            """
            INSERT INTO core_datasource
                (id, tenant_id, name, description, type, type_name, num)
            VALUES
                (101, 10, 'Tenant A DS', 'a', 'postgresql', 'PostgreSQL', '1'),
                (201, 20, 'Tenant B DS', 'b', 'postgresql', 'PostgreSQL', '1')
            """
        ))
        session.commit()

        current_assistant = AssistantHeader(
            id=101,
            tenant_id=10,
            name="Tenant A",
            type=0,
            domain="https://example.com",
            description="demo",
            configuration=json.dumps({}),
            custom_model=None,
            online=True,
        )
        rows = asyncio.run(assistant_api.ds(session=session, current_assistant=current_assistant))

        assert [row["id"] for row in rows] == [101]


def test_assistant_validator_token_contains_assistant_tenant_id():
    engine = _engine()
    with Session(engine) as session:
        assistant = _assistant(101, 10, "Tenant A")
        session.add(assistant)
        session.commit()

        result = asyncio.run(assistant_api.validator(
            request=_http_request(credential=_validator_credential(assistant)),
            session=session,
            trans=_trans,
            id=101,
            virtual=999,
        ))
        payload = jwt.decode(result.token, settings.SECRET_KEY, algorithms=[security.ALGORITHM])

        assert payload["tenant_id"] == 10


def test_assistant_info_hides_certificate_without_validator_credential():
    engine = _engine()
    with Session(engine) as session:
        assistant = _assistant(101, 10, "Tenant A")
        assistant.configuration = json.dumps({
            "public_list": [101],
            "certificate": [{"type": "custom", "source": "secret-token", "target": "header"}],
        })
        session.add(assistant)
        session.commit()

        result = asyncio.run(assistant_api.info(
            request=_http_request(),
            response=Response(),
            session=session,
            trans=_trans,
            id=101,
        ))

        public_config = json.loads(result.configuration)
        assert "certificate" not in public_config


def test_assistant_info_includes_certificate_with_validator_credential():
    engine = _engine()
    with Session(engine) as session:
        assistant = _assistant(101, 10, "Tenant A")
        assistant.configuration = json.dumps({
            "public_list": [101],
            "certificate": [{"type": "custom", "source": "secret-token", "target": "header"}],
        })
        session.add(assistant)
        session.commit()

        result = asyncio.run(assistant_api.info(
            request=_http_request(credential=_validator_credential(assistant)),
            response=Response(),
            session=session,
            trans=_trans,
            id=101,
        ))

        public_config = json.loads(result.configuration)
        assert public_config["certificate"][0]["source"] == "secret-token"


def test_assistant_validator_rejects_missing_credential():
    engine = _engine()
    with Session(engine) as session:
        session.add(_assistant(101, 10, "Tenant A"))
        session.commit()

        with pytest.raises(HTTPException) as exc:
            asyncio.run(assistant_api.validator(
                request=_http_request(),
                session=session,
                trans=_trans,
                id=101,
                virtual=999,
            ))

        assert exc.value.status_code == 401


def test_assistant_validator_rejects_wrong_origin():
    engine = _engine()
    with Session(engine) as session:
        assistant = _assistant(101, 10, "Tenant A")
        session.add(assistant)
        session.commit()

        with pytest.raises(RuntimeError):
            asyncio.run(assistant_api.validator(
                request=_http_request(
                    origin="https://evil.example.com",
                    credential=_validator_credential(assistant, origin="https://evil.example.com"),
                ),
                session=session,
                trans=_trans,
                id=101,
                virtual=999,
            ))


def test_assistant_validator_rejects_wrong_app_secret_signature():
    engine = _engine()
    with Session(engine) as session:
        assistant = _assistant(101, 10, "Tenant A")
        session.add(assistant)
        session.commit()
        credential = jwt.encode(
            {
                "assistant_id": assistant.id,
                "tenant_id": assistant.tenant_id,
                "origin": "https://example.com",
                "exp": datetime.now(timezone.utc) + timedelta(minutes=5),
            },
            "wrong-secret",
            algorithm=security.ALGORITHM,
        )

        with pytest.raises(HTTPException) as exc:
            asyncio.run(assistant_api.validator(
                request=_http_request(credential=credential),
                session=session,
                trans=_trans,
                id=101,
                virtual=999,
            ))

        assert exc.value.status_code == 401


def test_assistant_validator_rejects_unsigned_origin_binding():
    engine = _engine()
    with Session(engine) as session:
        assistant = _assistant(101, 10, "Tenant A")
        session.add(assistant)
        session.commit()
        credential = jwt.encode(
            {
                "assistant_id": assistant.id,
                "tenant_id": assistant.tenant_id,
                "exp": datetime.now(timezone.utc) + timedelta(minutes=5),
            },
            assistant.app_secret,
            algorithm=security.ALGORITHM,
        )

        with pytest.raises(HTTPException) as exc:
            asyncio.run(assistant_api.validator(
                request=_http_request(credential=credential),
                session=session,
                trans=_trans,
                id=101,
                virtual=999,
            ))

        assert exc.value.status_code == 401
