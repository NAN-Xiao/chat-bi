import asyncio
import inspect
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, create_engine

from apps.data_training.api import data_training as data_training_api
from apps.data_training.models.data_training_model import DataTraining, DataTrainingInfo
from apps.system.schemas.semantic_scope import SemanticRecordScopeEnum
from apps.terminology.api import terminology as terminology_api
from apps.terminology.models.terminology_model import Terminology, TerminologyInfo


def _engine():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    with engine.begin() as conn:
        conn.execute(text(
            """
            CREATE TABLE terminology (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tenant_id INTEGER NOT NULL DEFAULT 1,
                scope VARCHAR(32) NOT NULL DEFAULT 'TENANT',
                pid INTEGER,
                create_time DATETIME,
                word VARCHAR(255),
                description TEXT,
                embedding TEXT,
                specific_ds BOOLEAN,
                datasource_ids TEXT,
                enabled BOOLEAN
            )
            """
        ))
        conn.execute(text(
            """
            CREATE TABLE data_training (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tenant_id INTEGER NOT NULL DEFAULT 1,
                scope VARCHAR(32) NOT NULL DEFAULT 'TENANT',
                datasource INTEGER,
                create_time DATETIME,
                question VARCHAR(255),
                description TEXT,
                embedding TEXT,
                enabled BOOLEAN,
                advanced_application INTEGER
            )
            """
        ))
    return engine


def _platform_admin():
    return SimpleNamespace(id=1, system_role="system_admin", tenant_id=1, tenant_role="owner")


def _tenant_admin():
    return SimpleNamespace(id=2, system_role="viewer", tenant_id=10, tenant_role="admin")


def _trans(key):
    return key


def _unwrap(func):
    return inspect.unwrap(func)


def test_platform_admin_can_maintain_platform_terminology(monkeypatch):
    monkeypatch.setattr(
        "apps.terminology.curd.terminology.run_save_terminology_embeddings",
        lambda *args, **kwargs: None,
    )
    engine = _engine()
    with Session(engine) as session:
        term_id = asyncio.run(_unwrap(terminology_api.create_or_update)(
            session=session,
            current_user=_platform_admin(),
            trans=_trans,
            info=TerminologyInfo(
                word="Common KPI",
                description="Shared SaaS-level term.",
                other_words=["Shared KPI"],
                specific_ds=True,
                datasource_ids=[999],
            ),
        ))

        row = session.get(Terminology, term_id)
        assert row.tenant_id == 1
        assert row.scope == SemanticRecordScopeEnum.PLATFORM.value
        assert row.specific_ds is False
        assert row.datasource_ids == []

        asyncio.run(_unwrap(terminology_api.enable)(
            session=session,
            current_user=_platform_admin(),
            id=term_id,
            enabled=False,
            trans=_trans,
        ))
        assert session.get(Terminology, term_id).enabled is False

        with pytest.raises(HTTPException):
            asyncio.run(_unwrap(terminology_api.delete)(
                session=session,
                current_user=_tenant_admin(),
                id_list=[term_id],
            ))
        assert session.get(Terminology, term_id) is not None


def test_platform_admin_can_maintain_platform_sql_examples(monkeypatch):
    monkeypatch.setattr(
        "apps.data_training.curd.data_training.run_save_data_training_embeddings",
        lambda *args, **kwargs: None,
    )
    engine = _engine()
    with Session(engine) as session:
        training_id = asyncio.run(_unwrap(data_training_api.create_or_update)(
            session=session,
            current_user=_platform_admin(),
            trans=_trans,
            info=DataTrainingInfo(
                question="Show a safe select example",
                description="SELECT * FROM table_name LIMIT 100",
                datasource=999,
            ),
        ))

        row = session.get(DataTraining, training_id)
        assert row.tenant_id == 1
        assert row.scope == SemanticRecordScopeEnum.PLATFORM.value
        assert row.datasource is None
        assert row.advanced_application is None

        asyncio.run(_unwrap(data_training_api.enable)(
            session=session,
            current_user=_platform_admin(),
            id=training_id,
            enabled=False,
            trans=_trans,
        ))
        assert session.get(DataTraining, training_id).enabled is False

        with pytest.raises(HTTPException):
            asyncio.run(_unwrap(data_training_api.delete)(
                session=session,
                current_user=_tenant_admin(),
                id_list=[training_id],
            ))
        assert session.get(DataTraining, training_id) is not None
