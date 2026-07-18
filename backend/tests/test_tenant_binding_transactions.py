"""验证工作空间绑定可参与外层事务。"""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlmodel import Session, create_engine


@pytest.fixture
def engine(tmp_path) -> Engine:
    database_path = tmp_path / "tenant_binding_transactions.db"
    engine = create_engine(f"sqlite:///{database_path}")
    statements = [
        """
        CREATE TABLE sys_tenant (
            id BIGINT PRIMARY KEY, public_id TEXT, name TEXT, status BIGINT,
            plan TEXT, subscription_status TEXT, billing_mode TEXT,
            trial_end_time BIGINT, current_period_end_time BIGINT,
            contract_no TEXT, billing_contact TEXT, billing_email TEXT,
            subscription_note TEXT, create_time BIGINT, update_time BIGINT
        )
        """,
        """
        CREATE TABLE core_datasource (
            id BIGINT PRIMARY KEY, tenant_id BIGINT, name TEXT, description TEXT,
            type TEXT, type_name TEXT, configuration TEXT, create_time DATETIME,
            create_by BIGINT, status TEXT, num TEXT, table_relation TEXT,
            embedding TEXT, recommended_config BIGINT
        )
        """,
        """
        CREATE TABLE core_datasource_user (
            id BIGINT PRIMARY KEY, ds_id BIGINT, user_id BIGINT, role TEXT,
            create_by BIGINT, create_time DATETIME
        )
        """,
        """
        CREATE TABLE core_datasource_tenant_binding (
            id INTEGER PRIMARY KEY, tenant_id BIGINT, datasource_id BIGINT,
            create_by BIGINT, create_time DATETIME
        )
        """,
        "CREATE TABLE ds_permission (id BIGINT PRIMARY KEY, ds_id BIGINT)",
        """
        CREATE TABLE core_external_mcp_server (
            id BIGINT PRIMARY KEY, name TEXT, endpoint TEXT, description TEXT,
            auth_type TEXT, auth_header_name TEXT, auth_token TEXT, server_name TEXT,
            server_version TEXT, status BIGINT, credential_configured BOOLEAN,
            create_by BIGINT, update_by BIGINT, create_time BIGINT, update_time BIGINT
        )
        """,
        """
        CREATE TABLE core_external_mcp_tenant_binding (
            id INTEGER PRIMARY KEY, tenant_id BIGINT, external_mcp_server_id BIGINT,
            create_by BIGINT, create_time BIGINT
        )
        """,
    ]
    with engine.begin() as connection:
        for statement in statements:
            connection.execute(text(statement))
        connection.execute(text("INSERT INTO sys_tenant (id, status) VALUES (11, 1)"))
        connection.execute(
            text("INSERT INTO core_datasource (id, tenant_id, name) VALUES (101, 1, '测试数据源')")
        )
        connection.execute(
            text("INSERT INTO core_datasource (id, tenant_id, name) VALUES (102, 1, '替换数据源')")
        )
        connection.execute(
            text(
                "INSERT INTO core_external_mcp_server (id, name, endpoint, status) "
                "VALUES (201, '测试 MCP', 'https://example.test/mcp', 1)"
            )
        )
        connection.execute(
            text(
                "INSERT INTO core_external_mcp_server (id, name, endpoint, status) "
                "VALUES (202, '替换 MCP', 'https://example.test/mcp-replacement', 1)"
            )
        )
    yield engine
    engine.dispose()


@pytest.fixture
def session(engine: Engine) -> Session:
    with Session(engine) as db_session:
        yield db_session


@pytest.fixture
def user() -> SimpleNamespace:
    return SimpleNamespace(id=7)


def persisted_datasource_id(engine: Engine) -> int | None:
    from apps.datasource.crud.binding import get_bound_datasource_id_for_tenant

    with Session(engine) as verification_session:
        return get_bound_datasource_id_for_tenant(verification_session, 11)


def persisted_external_mcp_id(engine: Engine) -> int | None:
    from apps.external_mcp.crud import get_bound_external_mcp_id_for_tenant

    with Session(engine) as verification_session:
        return get_bound_external_mcp_id_for_tenant(verification_session, 11)


def persisted_datasource_tenant_id(engine: Engine, datasource_id: int) -> int:
    with Session(engine) as verification_session:
        tenant_id = verification_session.exec(
            text("SELECT tenant_id FROM core_datasource WHERE id = :datasource_id"),
            params={"datasource_id": datasource_id},
        ).one()[0]
    return int(tenant_id)


def test_datasource_binding_can_defer_commit(
    engine: Engine,
    session: Session,
    user: SimpleNamespace,
) -> None:
    from apps.datasource.crud.binding import (
        bind_tenant_to_datasource,
        get_bound_datasource_id_for_tenant,
    )

    commit = Mock(wraps=session.commit)
    refresh = Mock(wraps=session.refresh)
    session.commit = commit
    session.refresh = refresh

    bind_tenant_to_datasource(session, user, 11, 101, commit=False)

    commit.assert_not_called()
    refresh.assert_not_called()
    assert get_bound_datasource_id_for_tenant(session, 11) == 101
    session.rollback()
    assert persisted_datasource_id(engine) is None


def test_direct_datasource_binding_can_defer_commit(
    engine: Engine,
    session: Session,
    user: SimpleNamespace,
) -> None:
    from apps.datasource.crud.binding import bind_datasource_to_tenant, get_bound_datasource_id_for_tenant
    from apps.datasource.models.datasource import CoreDatasource

    commit = Mock(wraps=session.commit)
    refresh = Mock(wraps=session.refresh)
    session.commit = commit
    session.refresh = refresh

    datasource = session.get(CoreDatasource, 101)
    assert datasource is not None
    bind_datasource_to_tenant(session, user, datasource, 11, commit=False)

    commit.assert_not_called()
    refresh.assert_not_called()
    assert get_bound_datasource_id_for_tenant(session, 11) == 101
    session.rollback()
    assert persisted_datasource_id(engine) is None


def test_direct_datasource_clearing_can_defer_commit(
    engine: Engine,
    session: Session,
    user: SimpleNamespace,
) -> None:
    from apps.datasource.crud.binding import bind_datasource_to_tenant, get_bound_datasource_id_for_tenant
    from apps.datasource.models.datasource import CoreDatasource

    session.exec(
        text(
            "INSERT INTO core_datasource_tenant_binding "
            "(id, tenant_id, datasource_id) VALUES (1, 11, 101)"
        )
    )
    session.commit()
    commit = Mock(wraps=session.commit)
    refresh = Mock(wraps=session.refresh)
    session.commit = commit
    session.refresh = refresh
    datasource = session.get(CoreDatasource, 101)
    assert datasource is not None

    bind_datasource_to_tenant(session, user, datasource, None, commit=False)

    commit.assert_not_called()
    refresh.assert_not_called()
    assert get_bound_datasource_id_for_tenant(session, 11) is None
    session.rollback()
    assert persisted_datasource_id(engine) == 101


def test_clearing_datasource_binding_can_defer_commit(
    engine: Engine,
    session: Session,
    user: SimpleNamespace,
) -> None:
    from apps.datasource.crud.binding import bind_tenant_to_datasource, get_bound_datasource_id_for_tenant

    session.exec(
        text(
            "INSERT INTO core_datasource_tenant_binding "
            "(id, tenant_id, datasource_id) VALUES (1, 11, 101)"
        )
    )
    session.commit()
    commit = Mock(wraps=session.commit)
    session.commit = commit

    bind_tenant_to_datasource(session, user, 11, None, commit=False)

    commit.assert_not_called()
    assert get_bound_datasource_id_for_tenant(session, 11) is None
    session.rollback()
    assert persisted_datasource_id(engine) == 101


def test_legacy_datasource_clearing_can_defer_commit(
    engine: Engine,
    session: Session,
    user: SimpleNamespace,
) -> None:
    from apps.datasource.crud.binding import bind_tenant_to_datasource, get_bound_datasource_id_for_tenant

    session.exec(text("UPDATE core_datasource SET tenant_id = 11 WHERE id = 101"))
    session.exec(text("DROP TABLE core_datasource_tenant_binding"))
    session.commit()
    commit = Mock(wraps=session.commit)
    refresh = Mock(wraps=session.refresh)
    session.commit = commit
    session.refresh = refresh

    bind_tenant_to_datasource(session, user, 11, None, commit=False)

    commit.assert_not_called()
    refresh.assert_not_called()
    assert get_bound_datasource_id_for_tenant(session, 11) is None
    session.rollback()
    assert persisted_datasource_id(engine) == 101


def test_legacy_direct_datasource_binding_can_defer_commit(
    engine: Engine,
    session: Session,
    user: SimpleNamespace,
) -> None:
    from apps.datasource.crud.binding import bind_datasource_to_tenant
    from apps.datasource.models.datasource import CoreDatasource

    session.exec(text("DROP TABLE core_datasource_tenant_binding"))
    session.commit()
    commit = Mock(wraps=session.commit)
    refresh = Mock(wraps=session.refresh)
    session.commit = commit
    session.refresh = refresh
    datasource = session.get(CoreDatasource, 101)
    assert datasource is not None

    bind_datasource_to_tenant(session, user, datasource, 11, commit=False)

    commit.assert_not_called()
    refresh.assert_not_called()
    assert datasource.tenant_id == 11
    session.rollback()
    assert persisted_datasource_tenant_id(engine, 101) == 1


def test_replacing_datasource_binding_can_defer_commit(
    engine: Engine,
    session: Session,
    user: SimpleNamespace,
) -> None:
    from apps.datasource.crud.binding import bind_tenant_to_datasource, get_bound_datasource_id_for_tenant

    session.exec(
        text(
            "INSERT INTO core_datasource_tenant_binding "
            "(id, tenant_id, datasource_id) VALUES (1, 11, 101)"
        )
    )
    session.commit()
    commit = Mock(wraps=session.commit)
    refresh = Mock(wraps=session.refresh)
    session.commit = commit
    session.refresh = refresh

    bind_tenant_to_datasource(session, user, 11, 102, commit=False)

    commit.assert_not_called()
    refresh.assert_not_called()
    assert get_bound_datasource_id_for_tenant(session, 11) == 102
    session.rollback()
    assert persisted_datasource_id(engine) == 101


def test_external_mcp_binding_can_defer_commit(
    engine: Engine,
    session: Session,
    user: SimpleNamespace,
) -> None:
    from apps.external_mcp.crud import (
        bind_tenant_to_external_mcp,
        get_bound_external_mcp_id_for_tenant,
    )

    commit = Mock(wraps=session.commit)
    refresh = Mock(wraps=session.refresh)
    session.commit = commit
    session.refresh = refresh

    bind_tenant_to_external_mcp(session, user, 11, 201, commit=False)

    commit.assert_not_called()
    refresh.assert_not_called()
    assert get_bound_external_mcp_id_for_tenant(session, 11) == 201
    session.rollback()
    assert persisted_external_mcp_id(engine) is None


def test_clearing_external_mcp_binding_can_defer_commit(
    engine: Engine,
    session: Session,
    user: SimpleNamespace,
) -> None:
    from apps.external_mcp.crud import (
        bind_tenant_to_external_mcp,
        get_bound_external_mcp_id_for_tenant,
    )

    session.exec(
        text(
            "INSERT INTO core_external_mcp_tenant_binding "
            "(id, tenant_id, external_mcp_server_id) VALUES (1, 11, 201)"
        )
    )
    session.commit()
    commit = Mock(wraps=session.commit)
    session.commit = commit

    bind_tenant_to_external_mcp(session, user, 11, None, commit=False)

    commit.assert_not_called()
    assert get_bound_external_mcp_id_for_tenant(session, 11) is None
    session.rollback()
    assert persisted_external_mcp_id(engine) == 201


def test_updating_external_mcp_binding_can_defer_commit(
    engine: Engine,
    session: Session,
    user: SimpleNamespace,
) -> None:
    from apps.external_mcp.crud import (
        bind_tenant_to_external_mcp,
        get_bound_external_mcp_id_for_tenant,
    )

    session.exec(
        text(
            "INSERT INTO core_external_mcp_tenant_binding "
            "(id, tenant_id, external_mcp_server_id) VALUES (1, 11, 201)"
        )
    )
    session.commit()
    commit = Mock(wraps=session.commit)
    refresh = Mock(wraps=session.refresh)
    session.commit = commit
    session.refresh = refresh

    bind_tenant_to_external_mcp(session, user, 11, 202, commit=False)

    commit.assert_not_called()
    refresh.assert_not_called()
    assert get_bound_external_mcp_id_for_tenant(session, 11) == 202
    session.rollback()
    assert persisted_external_mcp_id(engine) == 201


@pytest.mark.parametrize("binding_kind", ["datasource", "external_mcp"])
def test_default_binding_still_commits(
    engine: Engine,
    session: Session,
    user: SimpleNamespace,
    binding_kind: str,
) -> None:
    if binding_kind == "datasource":
        from apps.datasource.crud.binding import bind_tenant_to_datasource

        bind_tenant_to_datasource(session, user, 11, 101)
        get_persisted_id = persisted_datasource_id
        expected_id = 101
    else:
        from apps.external_mcp.crud import bind_tenant_to_external_mcp

        bind_tenant_to_external_mcp(session, user, 11, 201)
        get_persisted_id = persisted_external_mcp_id
        expected_id = 201

    session.close()

    assert get_persisted_id(engine) == expected_id


def test_default_datasource_clearing_commits_without_refresh(
    engine: Engine,
    session: Session,
    user: SimpleNamespace,
) -> None:
    from apps.datasource.crud.binding import bind_tenant_to_datasource

    session.exec(
        text(
            "INSERT INTO core_datasource_tenant_binding "
            "(id, tenant_id, datasource_id) VALUES (1, 11, 101)"
        )
    )
    session.commit()
    refresh = Mock(wraps=session.refresh)
    session.refresh = refresh

    bind_tenant_to_datasource(session, user, 11, None)

    refresh.assert_not_called()
    session.close()

    assert persisted_datasource_id(engine) is None
