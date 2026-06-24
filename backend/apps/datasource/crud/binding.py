import datetime

from fastapi import HTTPException
from sqlalchemy import inspect
from sqlmodel import select

from apps.datasource.crud.permission_rules import delete_permission_records_for_datasources
from apps.datasource.models.datasource import CoreDatasource, CoreDatasourceTenantBinding, CoreDatasourceUser
from apps.system.crud.tenant import DEFAULT_TENANT_ID
from apps.system.models.tenant import TenantModel, TenantUserModel
from common.core.deps import CurrentUser, SessionDep


def supports_datasource_tenant_binding(session: SessionDep) -> bool:
    try:
        return inspect(session.connection()).has_table(CoreDatasourceTenantBinding.__tablename__)
    except Exception:
        return False


def _binding_table_exists(session: SessionDep) -> bool:
    return supports_datasource_tenant_binding(session)


def datasource_tenant_binding_has_rows(session: SessionDep) -> bool:
    if not _binding_table_exists(session):
        return False
    return session.exec(select(CoreDatasourceTenantBinding.id).limit(1)).first() is not None


def datasource_tenant_binding_active(session: SessionDep) -> bool:
    return datasource_tenant_binding_has_rows(session)


def _table_exists(session: SessionDep, table_name: str) -> bool:
    try:
        return inspect(session.connection()).has_table(table_name)
    except Exception:
        return False


def get_bound_datasource_id_for_tenant(session: SessionDep, tenant_id: int | None) -> int | None:
    if tenant_id is None or int(tenant_id) == DEFAULT_TENANT_ID:
        return None
    if datasource_tenant_binding_active(session):
        datasource_id = session.exec(
            select(CoreDatasourceTenantBinding.datasource_id)
            .where(CoreDatasourceTenantBinding.tenant_id == int(tenant_id))
            .order_by(CoreDatasourceTenantBinding.id)
        ).first()
        return int(datasource_id) if datasource_id is not None else None
    datasource_id = session.exec(
        select(CoreDatasource.id)
        .where(CoreDatasource.tenant_id == int(tenant_id))
        .order_by(CoreDatasource.id)
    ).first()
    return int(datasource_id) if datasource_id is not None else None


def list_bound_datasource_ids_for_tenant(session: SessionDep, tenant_id: int | None) -> set[int]:
    datasource_id = get_bound_datasource_id_for_tenant(session, tenant_id)
    return {datasource_id} if datasource_id is not None else set()


def list_bound_tenant_ids_for_datasource(session: SessionDep, datasource_id: int | None) -> list[int]:
    if datasource_id is None:
        return []
    if datasource_tenant_binding_active(session):
        rows = session.exec(
            select(CoreDatasourceTenantBinding.tenant_id)
            .where(CoreDatasourceTenantBinding.datasource_id == int(datasource_id))
            .order_by(CoreDatasourceTenantBinding.tenant_id)
        ).all()
        return [int(row) for row in rows if row is not None and int(row) != DEFAULT_TENANT_ID]
    datasource = session.get(CoreDatasource, int(datasource_id))
    tenant_id = int(datasource.tenant_id) if datasource and datasource.tenant_id else None
    return [tenant_id] if tenant_id and tenant_id != DEFAULT_TENANT_ID else []


def datasource_bound_to_tenant(session: SessionDep, datasource_id: int, tenant_id: int | None) -> bool:
    if tenant_id is None:
        return False
    if datasource_tenant_binding_active(session):
        return session.exec(
            select(CoreDatasourceTenantBinding.id).where(
                CoreDatasourceTenantBinding.tenant_id == int(tenant_id),
                CoreDatasourceTenantBinding.datasource_id == int(datasource_id),
            )
        ).first() is not None
    datasource = session.get(CoreDatasource, int(datasource_id))
    return bool(datasource and int(datasource.tenant_id or DEFAULT_TENANT_ID) == int(tenant_id))


def list_datasource_binding_rows(session: SessionDep, tenant_ids: list[int] | None = None):
    if datasource_tenant_binding_active(session):
        statement = (
            select(
                CoreDatasourceTenantBinding.tenant_id,
                CoreDatasourceTenantBinding.datasource_id,
                CoreDatasource.name,
            )
            .join(CoreDatasource, CoreDatasource.id == CoreDatasourceTenantBinding.datasource_id)
            .order_by(CoreDatasourceTenantBinding.tenant_id, CoreDatasource.name)
        )
        if tenant_ids:
            statement = statement.where(CoreDatasourceTenantBinding.tenant_id.in_([int(item) for item in tenant_ids]))
        return session.exec(statement).all()

    statement = (
        select(CoreDatasource.tenant_id, CoreDatasource.id, CoreDatasource.name)
        .where(CoreDatasource.tenant_id != DEFAULT_TENANT_ID)
        .order_by(CoreDatasource.tenant_id, CoreDatasource.name)
    )
    if tenant_ids:
        statement = statement.where(CoreDatasource.tenant_id.in_([int(item) for item in tenant_ids]))
    return session.exec(statement).all()


def _delete_datasource_users(
        session: SessionDep,
        datasource_ids: list[int],
        *,
        tenant_id: int | None = None,
) -> None:
    ids = [int(datasource_id) for datasource_id in datasource_ids if datasource_id is not None]
    if not ids:
        return
    query = session.query(CoreDatasourceUser).filter(CoreDatasourceUser.ds_id.in_(ids))
    if tenant_id is not None and _table_exists(session, TenantUserModel.__tablename__):
        tenant_user_ids = select(TenantUserModel.user_id).where(
            TenantUserModel.tenant_id == int(tenant_id),
            TenantUserModel.status == 1,
        )
        query = query.filter(CoreDatasourceUser.user_id.in_(tenant_user_ids))
    query.delete(synchronize_session=False)


def clear_datasource_workspace_permissions(
        session: SessionDep,
        datasource_ids: list[int],
        *,
        tenant_id: int | None = None,
) -> None:
    ids = [int(datasource_id) for datasource_id in datasource_ids if datasource_id is not None]
    if not ids:
        return
    _delete_datasource_users(session, ids, tenant_id=tenant_id)
    delete_permission_records_for_datasources(session, ids, tenant_id=tenant_id)


def bind_datasource_to_tenant(
        session: SessionDep,
        user: CurrentUser,
        datasource: CoreDatasource,
        tenant_id: int | None,
) -> CoreDatasource:
    target_tenant_id = int(tenant_id or DEFAULT_TENANT_ID)

    if target_tenant_id != DEFAULT_TENANT_ID:
        tenant = session.get(TenantModel, target_tenant_id)
        if tenant is None or int(getattr(tenant, "status", 1)) < 0:
            raise HTTPException(status_code=404, detail="工作空间不存在")

    if not _binding_table_exists(session):
        if target_tenant_id == DEFAULT_TENANT_ID:
            datasource.tenant_id = DEFAULT_TENANT_ID
            clear_datasource_workspace_permissions(session, [int(datasource.id)])
            session.add(datasource)
            session.commit()
            session.refresh(datasource)
            return datasource

        existing = session.exec(
            select(CoreDatasource).where(
                CoreDatasource.tenant_id == target_tenant_id,
                CoreDatasource.id != int(datasource.id),
            )
        ).all()
        existing_ids = [int(item.id) for item in existing]
        for item in existing:
            item.tenant_id = DEFAULT_TENANT_ID
            session.add(item)
        clear_datasource_workspace_permissions(session, existing_ids, tenant_id=target_tenant_id)

        if int(datasource.tenant_id or DEFAULT_TENANT_ID) != target_tenant_id:
            clear_datasource_workspace_permissions(session, [int(datasource.id)], tenant_id=target_tenant_id)
        datasource.tenant_id = target_tenant_id
        session.add(datasource)
        session.commit()
        session.refresh(datasource)
        return datasource

    if target_tenant_id == DEFAULT_TENANT_ID:
        bound_tenant_ids = list_bound_tenant_ids_for_datasource(session, int(datasource.id))
        session.query(CoreDatasourceTenantBinding).filter(
            CoreDatasourceTenantBinding.datasource_id == int(datasource.id)
        ).delete(synchronize_session=False)
        clear_datasource_workspace_permissions(session, [int(datasource.id)])
        if int(datasource.tenant_id or DEFAULT_TENANT_ID) in bound_tenant_ids:
            datasource.tenant_id = DEFAULT_TENANT_ID
            session.add(datasource)
        session.commit()
        session.refresh(datasource)
        return datasource

    existing_for_tenant = session.exec(
        select(CoreDatasourceTenantBinding).where(CoreDatasourceTenantBinding.tenant_id == target_tenant_id)
    ).first()
    if existing_for_tenant and int(existing_for_tenant.datasource_id) != int(datasource.id):
        clear_datasource_workspace_permissions(
            session,
            [int(existing_for_tenant.datasource_id)],
            tenant_id=target_tenant_id,
        )
        clear_datasource_workspace_permissions(session, [int(datasource.id)], tenant_id=target_tenant_id)
        existing_for_tenant.datasource_id = int(datasource.id)
        existing_for_tenant.create_by = getattr(user, "id", None)
        existing_for_tenant.create_time = datetime.datetime.now()
        session.add(existing_for_tenant)
    elif existing_for_tenant is None:
        clear_datasource_workspace_permissions(session, [int(datasource.id)], tenant_id=target_tenant_id)
        session.add(CoreDatasourceTenantBinding(
            tenant_id=target_tenant_id,
            datasource_id=int(datasource.id),
            create_by=getattr(user, "id", None),
            create_time=datetime.datetime.now(),
        ))

    if int(datasource.tenant_id or DEFAULT_TENANT_ID) == DEFAULT_TENANT_ID:
        datasource.tenant_id = target_tenant_id
        session.add(datasource)

    session.commit()
    session.refresh(datasource)
    return datasource


def bind_tenant_to_datasource(
        session: SessionDep,
        user: CurrentUser,
        tenant_id: int,
        datasource_id: int | None,
) -> CoreDatasource | None:
    target_tenant_id = int(tenant_id)
    if target_tenant_id == DEFAULT_TENANT_ID:
        raise HTTPException(status_code=400, detail="默认工作空间不能绑定数据源")
    tenant = session.get(TenantModel, target_tenant_id)
    if tenant is None or int(getattr(tenant, "status", 1)) < 0:
        raise HTTPException(status_code=404, detail="工作空间不存在")

    if datasource_id in (None, "", 0):
        current_datasource_id = get_bound_datasource_id_for_tenant(session, target_tenant_id)
        if current_datasource_id is None:
            return None
        if _binding_table_exists(session):
            session.query(CoreDatasourceTenantBinding).filter(
                CoreDatasourceTenantBinding.tenant_id == target_tenant_id
            ).delete(synchronize_session=False)
            clear_datasource_workspace_permissions(session, [current_datasource_id], tenant_id=target_tenant_id)
            datasource = session.get(CoreDatasource, current_datasource_id)
            if datasource and int(datasource.tenant_id or DEFAULT_TENANT_ID) == target_tenant_id:
                still_bound = session.exec(
                    select(CoreDatasourceTenantBinding.id).where(
                        CoreDatasourceTenantBinding.datasource_id == current_datasource_id
                    )
                ).first()
                if still_bound is None:
                    datasource.tenant_id = DEFAULT_TENANT_ID
                    session.add(datasource)
            session.commit()
        else:
            current = session.get(CoreDatasource, current_datasource_id)
            if current is not None:
                bind_datasource_to_tenant(session, user, current, None)
        return None

    datasource = session.get(CoreDatasource, int(datasource_id))
    if datasource is None:
        raise HTTPException(status_code=404, detail="数据源不存在")
    return bind_datasource_to_tenant(session, user, datasource, target_tenant_id)
