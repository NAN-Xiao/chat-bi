from sqlalchemy import text
from sqlmodel import Session, create_engine

from apps.data_training.curd.data_training import (
    get_all_data_training,
    get_training_template,
    page_data_training,
)
from apps.terminology.curd.terminology import (
    build_terminology_query,
    get_terminology_template,
)


def _engine_with_semantic_tables():
    engine = create_engine("sqlite://")
    with engine.begin() as conn:
        conn.execute(text(
            """
            CREATE TABLE core_datasource (
                id INTEGER PRIMARY KEY,
                tenant_id INTEGER NOT NULL DEFAULT 1,
                name VARCHAR(128) NOT NULL
            )
            """
        ))
        conn.execute(text(
            """
            CREATE TABLE sys_assistant (
                id INTEGER PRIMARY KEY,
                tenant_id INTEGER NOT NULL DEFAULT 1,
                name VARCHAR(255),
                type INTEGER NOT NULL DEFAULT 1
            )
            """
        ))
        conn.execute(text(
            """
            CREATE TABLE data_training (
                id INTEGER PRIMARY KEY,
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
        conn.execute(text(
            """
            CREATE TABLE terminology (
                id INTEGER PRIMARY KEY,
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
            INSERT INTO core_datasource (id, tenant_id, name)
            VALUES (1, 10, 'Workspace DS'), (2, 20, 'Other DS')
            """
        ))
        conn.execute(text(
            """
            INSERT INTO data_training
                (id, tenant_id, scope, datasource, create_time, question, description, enabled)
            VALUES
                (1, 1, 'PLATFORM', NULL, '2026-01-01', 'platform dau', 'platform sql', 1),
                (2, 10, 'TENANT', 1, '2026-01-02', 'workspace dau', 'workspace sql', 1),
                (3, 20, 'TENANT', 2, '2026-01-03', 'other dau', 'other sql', 1),
                (4, 1, 'TENANT', 1, '2026-01-04', 'wrong tenant dau', 'wrong tenant sql', 1)
            """
        ))
        conn.execute(text(
            """
            INSERT INTO terminology
                (id, tenant_id, scope, pid, create_time, word, description, specific_ds, datasource_ids, enabled)
            VALUES
                (1, 1, 'PLATFORM', NULL, '2026-01-01', 'platform term', 'platform desc', 0, '[]', 1),
                (2, 10, 'TENANT', NULL, '2026-01-02', 'workspace term', 'workspace desc', 0, '[]', 1),
                (3, 20, 'TENANT', NULL, '2026-01-03', 'other term', 'other desc', 0, '[]', 1)
            """
        ))
    return engine


def test_workspace_sql_management_hides_platform_and_other_workspace_examples():
    engine = _engine_with_semantic_tables()

    with Session(engine) as session:
        _page, _size, total, _pages, rows = page_data_training(
            session,
            current_page=1,
            page_size=10,
            name="dau",
            datasource_ids={1},
            tenant_id=10,
        )

    assert total == 1
    assert [row.question for row in rows] == ["workspace dau"]


def test_runtime_sql_recall_can_include_platform_examples(monkeypatch):
    monkeypatch.setattr(
        "apps.data_training.curd.data_training.settings.EMBEDDING_ENABLED",
        False,
    )
    engine = _engine_with_semantic_tables()

    with Session(engine) as session:
        _template, with_platform = get_training_template(
            session,
            "platform dau",
            datasource=1,
            tenant_id=10,
            include_platform=True,
        )
        _template, without_platform = get_training_template(
            session,
            "platform dau",
            datasource=1,
            tenant_id=10,
            include_platform=False,
        )

    assert [item["question"] for item in with_platform] == ["platform dau"]
    assert without_platform == []


def test_workspace_terminology_management_hides_platform_terms():
    engine = _engine_with_semantic_tables()

    with Session(engine) as session:
        _stmt, total, _pages, _page, _size, _can_platform, _can_tenant = build_terminology_query(
            session,
            name="term",
            current_page=1,
            page_size=10,
            accessible_datasource_ids=None,
            tenant_id=10,
            include_global=True,
        )

    assert total == 1


def test_runtime_terminology_recall_can_include_platform_terms(monkeypatch):
    monkeypatch.setattr(
        "apps.terminology.curd.terminology.settings.EMBEDDING_ENABLED",
        False,
    )
    engine = _engine_with_semantic_tables()

    with Session(engine) as session:
        _template, with_platform = get_terminology_template(
            session,
            "platform term",
            datasource=None,
            tenant_id=10,
            include_platform=True,
        )
        _template, without_platform = get_terminology_template(
            session,
            "platform term",
            datasource=None,
            tenant_id=10,
            include_platform=False,
        )

    assert [item["words"][0] for item in with_platform] == ["platform term"]
    assert without_platform == []


def test_export_uses_same_workspace_sql_visibility():
    engine = _engine_with_semantic_tables()

    with Session(engine) as session:
        rows = get_all_data_training(
            session,
            name="dau",
            datasource_ids={1},
            tenant_id=10,
        )
        _stmt, term_total, _pages, _page, _size, _can_platform, _can_tenant = build_terminology_query(
            session,
            name="term",
            accessible_datasource_ids=None,
            tenant_id=10,
            include_global=True,
        )

    assert [row.question for row in rows] == ["workspace dau"]
    assert term_total == 1
