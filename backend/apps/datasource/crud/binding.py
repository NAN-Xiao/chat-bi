from fastapi import HTTPException
from sqlmodel import select

from apps.datasource.crud.permission_rules import delete_permission_records_for_datasources
from apps.datasource.models.datasource import CoreDatasource, CoreDatasourceUser
from apps.system.crud.tenant import DEFAULT_TENANT_ID
from apps.system.models.tenant import TenantModel
from common.core.deps import CurrentUser, SessionDep


def _delete_datasource_users(session: SessionDep, datasource_ids: list[int]) -> None:
    ids = [int(datasource_id) for datasource_id in datasource_ids if datasource_id is not None]
    if not ids:
        return
    session.query(CoreDatasourceUser).filter(CoreDatasourceUser.ds_id.in_(ids)).delete(synchronize_session=False)


def clear_datasource_workspace_permissions(session: SessionDep, datasource_ids: list[int]) -> None:
    ids = [int(datasource_id) for datasource_id in datasource_ids if datasource_id is not None]
    if not ids:
        return
    _delete_datasource_users(session, ids)
    delete_permission_records_for_datasources(session, ids)


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
    clear_datasource_workspace_permissions(session, existing_ids)

    if int(datasource.tenant_id or DEFAULT_TENANT_ID) != target_tenant_id:
        clear_datasource_workspace_permissions(session, [int(datasource.id)])
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

    current = session.exec(
        select(CoreDatasource).where(CoreDatasource.tenant_id == target_tenant_id)
    ).first()
    if datasource_id in (None, "", 0):
        if current is None:
            return None
        bind_datasource_to_tenant(session, user, current, None)
        return None

    datasource = session.get(CoreDatasource, int(datasource_id))
    if datasource is None:
        raise HTTPException(status_code=404, detail="数据源不存在")
    return bind_datasource_to_tenant(session, user, datasource, target_tenant_id)
