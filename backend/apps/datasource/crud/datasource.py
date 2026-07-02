"""
脚本说明：这个脚本封装数据源的增删改查和保存逻辑，让接口层不直接处理太多细节。
"""
import datetime
import json
from typing import List

from fastapi import HTTPException
from sqlalchemy import and_, text
from sqlmodel import select

from apps.datasource.crud.permission import can_access_table, current_tenant_id, get_accessible_datasource_ids, \
    get_column_permission_fields, get_row_permission_filters, get_user_permission_rules, get_user_scoped_table_ids, \
    has_datasource_access, is_normal_user
from apps.datasource.crud.binding import datasource_bound_to_tenant
from apps.datasource.crud.query_executor import execute_user_query_or_raise
from apps.datasource.embedding.table_embedding import calc_table_embedding
from apps.datasource.utils.utils import aes_decrypt, effective_db_schema, encrypt_datasource_configuration
from apps.db.constant import DB
from apps.db.db import get_tables, get_fields, check_connection
from apps.db.engine import get_engine_config, get_engine_conn
from apps.system.crud.schema_metadata import (
    SchemaFieldKey,
    field_comment_map,
    save_field_comment,
    save_table_comment,
    table_comment_map,
)
from apps.system.crud.tenant import DEFAULT_TENANT_ID
from apps.system.crud.user import is_platform_admin, is_platform_workspace_delegate
from apps.system.schemas.auth import CacheName, CacheNamespace
from common.core.config import settings
from common.core.deps import SessionDep, CurrentUser, Trans
from common.utils.embedding_threads import run_save_table_embeddings, run_save_ds_embeddings
from common.utils.utils import deepcopy_ignore_extra, equals_ignore_case
from common.core.app_cache import clear_cache
from .table import get_tables_by_ds_id
from ..crud.field import delete_field_by_ds_id, update_field
from ..crud.table import delete_table_by_ds_id, update_table
from ..models.datasource import CoreDatasource, CreateDatasource, CoreTable, CoreField, ColumnSchema, TableObj, \
    CoreDatasourceUser, DatasourceConf, TableAndFields


def get_datasource_list(session: SessionDep, user: CurrentUser) -> List[CoreDatasource]:
    """
    是什么：get_datasource_list 是一个可以复用的小步骤，负责数据源相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把数据源需要的数据找出来，整理成后面好用的样子。
    """
    if is_platform_admin(user) and not is_platform_workspace_delegate(user):
        return session.exec(select(CoreDatasource).order_by(CoreDatasource.name)).all()

    tenant_id = current_tenant_id(user)
    accessible_ids = get_accessible_datasource_ids(session, user)
    if not accessible_ids:
        return []

    statement = select(CoreDatasource).where(CoreDatasource.id.in_(accessible_ids))
    return session.exec(statement.order_by(CoreDatasource.name)).all()


def get_ds(session: SessionDep, id: int, user: CurrentUser | None = None):
    """
    是什么：get_ds 是一个可以复用的小步骤，负责数据源相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把数据源需要的数据找出来，整理成后面好用的样子。
    """
    statement = select(CoreDatasource).where(CoreDatasource.id == id)
    tenant_id = None if is_platform_admin(user) and not is_platform_workspace_delegate(user) else current_tenant_id(user)
    datasource = session.exec(statement).first()
    if datasource is not None and tenant_id is not None and not datasource_bound_to_tenant(session, int(datasource.id), tenant_id):
        return None
    return datasource


def check_status_by_id(session: SessionDep, trans: Trans, ds_id: int, is_raise: bool = False):
    """
    是什么：check_status_by_id 是一个可以复用的小步骤，负责数据源相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：检查数据源里的数据、权限或配置是否合法，不对就及时拦住。
    """
    ds = session.get(CoreDatasource, ds_id)
    if ds is None:
        if is_raise:
            raise HTTPException(status_code=500, detail=trans('i18n_ds_invalid'))
        return False
    return check_status(session, trans, ds, is_raise)


def check_status(session: SessionDep, trans: Trans, ds: CoreDatasource, is_raise: bool = False):
    """
    是什么：check_status 是一个可以复用的小步骤，负责数据源相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：检查数据源里的数据、权限或配置是否合法，不对就及时拦住。
    """
    return check_connection(trans, ds, is_raise)


def _datasource_tenant_id(session: SessionDep, ds_id: int | None) -> int | None:
    """
    是什么：_datasource_tenant_id 是一个可以复用的小步骤，负责数据源相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把数据源里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    if ds_id is None:
        return None
    return session.execute(select(CoreDatasource.tenant_id).where(CoreDatasource.id == ds_id)).scalar()


def _coerce_tenant_id(value) -> int | None:
    """
    是什么：_coerce_tenant_id 是一个可以复用的小步骤，负责数据源相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把数据源里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    try:
        if value in (None, ""):
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _schema_metadata_tenant_id(
        session: SessionDep,
        ds: CoreDatasource,
        current_user: CurrentUser | None = None,
        tenant_id: int | None = None,
) -> int | None:
    """
    是什么：_schema_metadata_tenant_id 是一个可以复用的小步骤，负责数据源相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把数据源里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    explicit_tenant_id = _coerce_tenant_id(tenant_id)
    if explicit_tenant_id is not None and datasource_bound_to_tenant(session, int(ds.id), explicit_tenant_id):
        return explicit_tenant_id

    user_tenant_id = current_tenant_id(current_user)
    if user_tenant_id is not None and datasource_bound_to_tenant(session, int(ds.id), user_tenant_id):
        return int(user_tenant_id)

    return _coerce_tenant_id(getattr(ds, "tenant_id", None))


def _apply_workspace_comments_to_tables(
        session: SessionDep,
        tenant_id: int | None,
        tables: list[CoreTable],
) -> list[CoreTable]:
    """
    是什么：_apply_workspace_comments_to_tables 是一个可以复用的小步骤，负责数据源相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把数据源里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    comments = table_comment_map(session, tenant_id, [table.table_name for table in tables])
    for table in tables:
        if table.table_name in comments:
            table.custom_comment = comments[table.table_name] or ""
        else:
            table.custom_comment = table.custom_comment or ""
    return tables


def _apply_workspace_comments_to_fields(
        session: SessionDep,
        tenant_id: int | None,
        table: CoreTable,
        fields: list[CoreField],
) -> list[CoreField]:
    """
    是什么：_apply_workspace_comments_to_fields 是一个可以复用的小步骤，负责数据源相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把数据源里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    comments = field_comment_map(
        session,
        tenant_id,
        [SchemaFieldKey(table.table_name, field.field_name) for field in fields],
    )
    for field in fields:
        key = (table.table_name, field.field_name)
        if key in comments:
            field.custom_comment = comments[key] or ""
        else:
            field.custom_comment = field.custom_comment or ""
    return fields


def check_name(session: SessionDep, trans: Trans, user: CurrentUser, ds: CoreDatasource):
    """
    是什么：check_name 是一个可以复用的小步骤，负责数据源相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：检查数据源里的数据、权限或配置是否合法，不对就及时拦住。
    """
    tenant_id = None if is_platform_admin(user) and not is_platform_workspace_delegate(user) else current_tenant_id(user)
    filters = [CoreDatasource.name == ds.name]
    if tenant_id is not None:
        filters.append(CoreDatasource.tenant_id == tenant_id)
    if ds.id is not None:
        ds_list = session.query(CoreDatasource).filter(
            and_(*filters, CoreDatasource.id != ds.id)).all()
        if ds_list is not None and len(ds_list) > 0:
            raise HTTPException(status_code=500, detail=trans('i18n_ds_name_exist'))
    else:
        ds_list = session.query(CoreDatasource).filter(and_(*filters)).all()
        if ds_list is not None and len(ds_list) > 0:
            raise HTTPException(status_code=500, detail=trans('i18n_ds_name_exist'))


@clear_cache(namespace=CacheNamespace.AUTH_INFO, cacheName=CacheName.DS_ID_LIST, keyExpression="user.id")
async def create_ds(session: SessionDep, trans: Trans, user: CurrentUser, create_ds: CreateDatasource):
    """
    是什么：create_ds 是一个可以复用的小步骤，负责数据源相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：创建或保存数据源需要的东西，让后续流程能继续往下走。
    """
    ds = CoreDatasource()
    deepcopy_ignore_extra(create_ds, ds)
    check_name(session, trans, user, ds)
    ds.tenant_id = (
        DEFAULT_TENANT_ID
        if is_platform_admin(user) and not is_platform_workspace_delegate(user)
        else current_tenant_id(user)
    )
    ds.create_time = datetime.datetime.now()
    # status = check_status(session, ds)
    ds.create_by = user.id
    ds.status = "Success"
    ds.type_name = DB.get_db(ds.type).db_name
    ds.configuration = encrypt_datasource_configuration(ds.configuration)
    record = CoreDatasource(**ds.model_dump())
    session.add(record)
    session.flush()
    session.refresh(record)
    ds.id = record.id
    session.commit()

    # 保存表和字段
    sync_table(session, ds, create_ds.tables)
    updateNum(session, ds)
    return ds


def chooseTables(session: SessionDep, trans: Trans, id: int, tables: List[CoreTable]):
    """
    是什么：chooseTables 是一个可以复用的小步骤，负责数据源相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把数据源里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    ds = session.query(CoreDatasource).filter(CoreDatasource.id == id).first()
    check_status(session, trans, ds, True)
    sync_table(session, ds, tables)
    updateNum(session, ds)


def update_ds(session: SessionDep, trans: Trans, user: CurrentUser, ds: CoreDatasource):
    """
    是什么：update_ds 是一个可以复用的小步骤，负责数据源相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把数据源相关的信息改成最新状态，并保存这些变化。
    """
    ds.id = int(ds.id)
    check_name(session, trans, user, ds)
    # status = check_status(session, trans, ds)
    ds.status = "Success"
    record = get_ds(session, ds.id, user)
    if record is None:
        raise HTTPException(status_code=404, detail="项目不存在")
    update_data = ds.model_dump(exclude_unset=True, exclude={"tenant_id", "embedding"})
    if update_data.get("configuration") in (None, ""):
        update_data.pop("configuration", None)
    elif "configuration" in update_data:
        update_data["configuration"] = encrypt_datasource_configuration(update_data["configuration"])
    for field, value in update_data.items():
        setattr(record, field, value)
    session.add(record)
    session.commit()

    run_save_ds_embeddings([ds.id], tenant_id=record.tenant_id)
    return ds


def update_ds_recommended_config(session: SessionDep, datasource_id: int, recommended_config: int):
    """
    是什么：update_ds_recommended_config 是一个可以复用的小步骤，负责数据源相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把数据源相关的信息改成最新状态，并保存这些变化。
    """
    record = session.exec(select(CoreDatasource).where(CoreDatasource.id == datasource_id)).first()
    record.recommended_config = recommended_config
    session.add(record)
    session.commit()


async def delete_ds(session: SessionDep, id: int, user: CurrentUser | None = None):
    """
    是什么：delete_ds 是一个可以复用的小步骤，负责数据源相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把数据源不再需要的数据、缓存或临时内容清理掉。
    """
    term = get_ds(session, id, user)
    if term is None:
        raise HTTPException(status_code=404, detail="项目不存在")
    if term.type == "excel":
        # 删除当前数据源下的全部表
        engine = get_engine_conn()
        conf = DatasourceConf(**json.loads(aes_decrypt(term.configuration)))
        with engine.connect() as conn:
            for sheet in conf.sheets:
                conn.execute(text(f'DROP TABLE IF EXISTS "{sheet["tableName"]}"'))
            conn.commit()

    session.query(CoreDatasourceUser).filter(CoreDatasourceUser.ds_id == id).delete(synchronize_session=False)
    session.delete(term)
    session.commit()
    delete_table_by_ds_id(session, id)
    delete_field_by_ds_id(session, id)
    return {
        "message": f"项目 {id} 已删除。"
    }


def getTables(session: SessionDep, id: int):
    """
    是什么：getTables 是一个可以复用的小步骤，负责数据源相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把数据源需要的数据找出来，整理成后面好用的样子。
    """
    ds = session.exec(select(CoreDatasource).where(CoreDatasource.id == id)).first()
    tables = get_tables(ds)
    return tables


def getTablesByDs(session: SessionDep, ds: CoreDatasource):
    # check_status(session, ds, True)
    """
    是什么：getTablesByDs 是一个可以复用的小步骤，负责数据源相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把数据源需要的数据找出来，整理成后面好用的样子。
    """
    tables = get_tables(ds)
    return tables


def getFields(session: SessionDep, id: int, table_name: str):
    """
    是什么：getFields 是一个可以复用的小步骤，负责数据源相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把数据源需要的数据找出来，整理成后面好用的样子。
    """
    ds = session.exec(select(CoreDatasource).where(CoreDatasource.id == id)).first()
    fields = get_fields(ds, table_name)
    return fields


def getFieldsByDs(session: SessionDep, ds: CoreDatasource, table_name: str):
    """
    是什么：getFieldsByDs 是一个可以复用的小步骤，负责数据源相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把数据源需要的数据找出来，整理成后面好用的样子。
    """
    fields = get_fields(ds, table_name)
    return fields


def sync_single_fields(
        session: SessionDep,
        trans: Trans,
        id: int,
        *,
        schedule_embeddings: bool = True,
        tenant_id: int | None = None,
):
    """
    是什么：sync_single_fields 是一个可以复用的小步骤，负责数据源相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把数据源相关的信息改成最新状态，并保存这些变化。
    """
    table_query = session.query(CoreTable).filter(CoreTable.id == id)
    if tenant_id is not None:
        table_query = table_query.join(CoreDatasource, CoreDatasource.id == CoreTable.ds_id).filter(
            CoreDatasource.tenant_id == int(tenant_id)
        )
    table = table_query.first()
    if table is None:
        raise HTTPException(status_code=404, detail="Table not found")
    ds = session.query(CoreDatasource).filter(CoreDatasource.id == table.ds_id).first()

    tables = getTablesByDs(session, ds)
    t_name = []
    for _t in tables:
        t_name.append(_t.tableName)

    if not table.table_name in t_name:
        raise HTTPException(status_code=500, detail=trans('i18n_table_not_exist'))

    # 同步字段
    fields = getFieldsByDs(session, ds, table.table_name)
    sync_fields(session, ds, table, fields)

    if schedule_embeddings:
        run_save_table_embeddings([table.id], tenant_id=ds.tenant_id)
        run_save_ds_embeddings([ds.id], tenant_id=ds.tenant_id)
    return {
        "table": table.table_name,
        "table_id": table.id,
        "datasource": ds.id,
        "field_count": len(fields),
    }


def sync_table(session: SessionDep, ds: CoreDatasource, tables: List[CoreTable]):
    """
    是什么：sync_table 是一个可以复用的小步骤，负责数据源相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把数据源相关的信息改成最新状态，并保存这些变化。
    """
    id_list = []
    for item in tables:
        statement = select(CoreTable).where(and_(CoreTable.ds_id == ds.id, CoreTable.table_name == item.table_name))
        record = session.exec(statement).first()
        # 更新已存在的表，仅更新表注释。
        if record is not None:
            item.id = record.id
            id_list.append(record.id)

            record.table_comment = item.table_comment
            session.add(record)
            session.commit()
        else:
            # 保存新表
            table = CoreTable(ds_id=ds.id, checked=True, table_name=item.table_name, table_comment=item.table_comment,
                              custom_comment="")
            session.add(table)
            session.flush()
            session.refresh(table)
            item.id = table.id
            id_list.append(table.id)
            session.commit()

        # 同步字段
        fields = getFieldsByDs(session, ds, item.table_name)
        sync_fields(session, ds, item, fields)

    if len(id_list) > 0:
        session.query(CoreTable).filter(and_(CoreTable.ds_id == ds.id, CoreTable.id.not_in(id_list))).delete(
            synchronize_session=False)
        session.query(CoreField).filter(and_(CoreField.ds_id == ds.id, CoreField.table_id.not_in(id_list))).delete(
            synchronize_session=False)
        session.commit()
    else:  # 删除该数据源下的全部表和字段
        session.query(CoreTable).filter(CoreTable.ds_id == ds.id).delete(synchronize_session=False)
        session.query(CoreField).filter(CoreField.ds_id == ds.id).delete(synchronize_session=False)
        session.commit()

    # 执行表向量化
    run_save_table_embeddings(id_list, tenant_id=ds.tenant_id)
    run_save_ds_embeddings([ds.id], tenant_id=ds.tenant_id)


def sync_fields(session: SessionDep, ds: CoreDatasource, table: CoreTable, fields: List[ColumnSchema]):
    """
    是什么：sync_fields 是一个可以复用的小步骤，负责数据源相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把数据源相关的信息改成最新状态，并保存这些变化。
    """
    id_list = []
    for index, item in enumerate(fields):
        statement = select(CoreField).where(
            and_(CoreField.table_id == table.id, CoreField.field_name == item.fieldName))
        record = session.exec(statement).first()
        if record is not None:
            item.id = record.id
            id_list.append(record.id)

            record.field_comment = item.fieldComment
            record.field_index = index
            record.field_type = item.fieldType
            session.add(record)
            session.commit()
        else:
            field = CoreField(ds_id=ds.id, table_id=table.id, checked=True, field_name=item.fieldName,
                              field_type=item.fieldType, field_comment=item.fieldComment,
                              custom_comment="", field_index=index)
            session.add(field)
            session.flush()
            session.refresh(field)
            item.id = field.id
            id_list.append(field.id)
            session.commit()

    if len(id_list) > 0:
        session.query(CoreField).filter(and_(CoreField.table_id == table.id, CoreField.id.not_in(id_list))).delete(
            synchronize_session=False)
        session.commit()


def update_table_and_fields(
        session: SessionDep,
        data: TableObj,
        current_user_id: int | None = None,
        tenant_id: int | None = None,
):
    """
    是什么：update_table_and_fields 是一个可以复用的小步骤，负责数据源相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把数据源相关的信息改成最新状态，并保存这些变化。
    """
    update_table(session, data.table)
    metadata_tenant_id = _coerce_tenant_id(tenant_id) or _datasource_tenant_id(session, data.table.ds_id)
    save_table_comment(
        session,
        metadata_tenant_id,
        data.table.table_name,
        data.table.custom_comment,
        current_user_id=current_user_id,
    )
    for field in data.fields:
        update_field(session, field)
        save_field_comment(
            session,
            metadata_tenant_id,
            data.table.table_name,
            field.field_name,
            field.custom_comment,
            current_user_id=current_user_id,
        )
    session.commit()

    run_save_table_embeddings([data.table.id], tenant_id=metadata_tenant_id)
    run_save_ds_embeddings([data.table.ds_id], tenant_id=metadata_tenant_id)


def updateTable(
        session: SessionDep,
        table: CoreTable,
        current_user_id: int | None = None,
        tenant_id: int | None = None,
):
    """
    是什么：updateTable 是一个可以复用的小步骤，负责数据源相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把数据源相关的信息改成最新状态，并保存这些变化。
    """
    update_table(session, table)

    metadata_tenant_id = _coerce_tenant_id(tenant_id) or _datasource_tenant_id(session, table.ds_id)
    save_table_comment(
        session,
        metadata_tenant_id,
        table.table_name,
        table.custom_comment,
        current_user_id=current_user_id,
    )
    session.commit()
    run_save_table_embeddings([table.id], tenant_id=metadata_tenant_id)
    run_save_ds_embeddings([table.ds_id], tenant_id=metadata_tenant_id)


def updateField(
        session: SessionDep,
        field: CoreField,
        current_user_id: int | None = None,
        tenant_id: int | None = None,
):
    """
    是什么：updateField 是一个可以复用的小步骤，负责数据源相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把数据源相关的信息改成最新状态，并保存这些变化。
    """
    update_field(session, field)

    metadata_tenant_id = _coerce_tenant_id(tenant_id) or _datasource_tenant_id(session, field.ds_id)
    table = session.get(CoreTable, field.table_id)
    if table is not None:
        save_field_comment(
            session,
            metadata_tenant_id,
            table.table_name,
            field.field_name,
            field.custom_comment,
            current_user_id=current_user_id,
        )
        session.commit()
    run_save_table_embeddings([field.table_id], tenant_id=metadata_tenant_id)
    run_save_ds_embeddings([field.ds_id], tenant_id=metadata_tenant_id)


def preview(session: SessionDep, current_user: CurrentUser, id: int, data: TableObj):
    """
    是什么：preview 是一个可以复用的小步骤，负责数据源相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把数据源里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    ds = session.query(CoreDatasource).filter(CoreDatasource.id == id).first()
    # check_status(session, ds, True)

    # 忽略入参中的字段列表，改从数据库查询字段。
    if not data.table.id:
        return {"fields": [], "data": [], "sql": ''}

    table = session.query(CoreTable).filter(
        and_(CoreTable.id == data.table.id, CoreTable.ds_id == ds.id)
    ).first()
    if table is None:
        return {"fields": [], "data": [], "sql": ''}

    contain_rules = get_user_permission_rules(session, current_user, ds.id) if is_normal_user(current_user) else []
    if not can_access_table(session, current_user, ds.id, table.id, contain_rules):
        return {"fields": [], "data": [], "sql": ''}

    fields = session.query(CoreField).filter(CoreField.table_id == data.table.id).order_by(
        CoreField.field_index.asc()).all()

    if fields is None or len(fields) == 0:
        return {"fields": [], "data": [], "sql": ''}

    where = ''
    f_list = [f for f in fields if f.checked]
    if is_normal_user(current_user):
        # 列已校验，同时对入参字段执行列权限过滤。
        f_list = get_column_permission_fields(session=session, current_user=current_user, table=table,
                                              fields=f_list, contain_rules=contain_rules)

        # 行权限树
        where_str = ''
        filter_mapping = get_row_permission_filters(session=session, current_user=current_user, ds=ds, tables=None,
                                                    single_table=table)
        if filter_mapping:
            mapping_dict = filter_mapping[0]
            where_str = mapping_dict.get('filter')
        where = (' where ' + where_str) if where_str is not None and where_str != '' else ''

    fields = [f.field_name for f in f_list]
    if fields is None or len(fields) == 0:
        return {"fields": [], "data": [], "sql": ''}

    conf = DatasourceConf(**json.loads(aes_decrypt(ds.configuration))) if ds.type != "excel" else get_engine_config()
    db_schema = effective_db_schema(ds.type, conf)
    sql: str = ""
    if ds.type == "mysql" or ds.type == "doris" or ds.type == "starrocks" or ds.type == "hive":
        sql = f"""SELECT `{"`, `".join(fields)}` FROM `{table.table_name}`
            {where}
            LIMIT 100"""
    elif ds.type == "sqlServer":
        sql = f"""SELECT TOP 100 [{"], [".join(fields)}] FROM [{db_schema}].[{table.table_name}]
            {where}
            """
    elif ds.type == "pg" or ds.type == "excel" or ds.type == "redshift" or ds.type == "kingbase":
        sql = f"""SELECT "{'", "'.join(fields)}" FROM "{db_schema}"."{table.table_name}"
            {where}
            LIMIT 100"""
    elif ds.type == "oracle":
        # sql = f"""SELECT "{'", "'.join(fields)}" FROM "{db_schema}"."{data.table.table_name}"
        #     {where}
        #     ORDER BY "{fields[0]}"
        #     OFFSET 0 ROWS FETCH NEXT 100 ROWS ONLY"""
        sql = f"""SELECT * FROM
                    (SELECT "{'", "'.join(fields)}" FROM "{db_schema}"."{table.table_name}"
                    {where}
                    ORDER BY "{fields[0]}")
                    WHERE ROWNUM <= 100
                    """
    elif ds.type == "ck":
        sql = f"""SELECT "{'", "'.join(fields)}" FROM "{table.table_name}"
            {where}
            LIMIT 100"""
    elif ds.type == "dm":
        sql = f"""SELECT "{'", "'.join(fields)}" FROM "{db_schema}"."{table.table_name}"
            {where}
            LIMIT 100"""
    elif ds.type == "es":
        sql = f"""SELECT "{'", "'.join(fields)}" FROM "{table.table_name}"
            {where}
            LIMIT 100"""
    return execute_user_query_or_raise(
        session=session,
        current_user=current_user,
        datasource=ds,
        sql=sql,
        allowed_tables=[table.table_name],
        origin_column=True,
        apply_row_permissions=False,
        validate_columns=False,
    ).result


def fieldEnum(session: SessionDep, current_user: CurrentUser, id: int):
    """
    是什么：fieldEnum 是一个可以复用的小步骤，负责数据源相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把数据源里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    field = session.query(CoreField).filter(CoreField.id == id).first()
    if field is None:
        return []
    table = session.query(CoreTable).filter(CoreTable.id == field.table_id).first()
    if table is None:
        return []
    ds = session.query(CoreDatasource).filter(CoreDatasource.id == table.ds_id).first()
    if ds is None:
        return []

    db = DB.get_db(ds.type)
    sql = f"""SELECT DISTINCT {db.prefix}{field.field_name}{db.suffix} FROM {db.prefix}{table.table_name}{db.suffix}"""
    res = execute_user_query_or_raise(
        session=session,
        current_user=current_user,
        datasource=ds,
        sql=sql,
        allowed_tables=[table.table_name],
        origin_column=True,
        validate_columns=False,
    ).result
    return [item.get(res.get('fields')[0]) for item in res.get('data')]


def updateNum(session: SessionDep, ds: CoreDatasource):
    """
    是什么：updateNum 是一个可以复用的小步骤，负责数据源相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把数据源相关的信息改成最新状态，并保存这些变化。
    """
    all_tables = get_tables(ds) if ds.type != 'excel' else json.loads(aes_decrypt(ds.configuration)).get('sheets')
    selected_tables = get_tables_by_ds_id(session, ds.id)
    num = f'{len(selected_tables)}/{len(all_tables)}'

    record = session.exec(select(CoreDatasource).where(CoreDatasource.id == ds.id)).first()
    update_data = ds.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(record, field, value)
    record.num = num
    session.add(record)
    session.commit()


def get_table_obj_by_ds(session: SessionDep, current_user: CurrentUser, ds: CoreDatasource) -> List[TableAndFields]:
    """
    是什么：get_table_obj_by_ds 是一个可以复用的小步骤，负责数据源相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把数据源需要的数据找出来，整理成后面好用的样子。
    """
    _list: List = []
    if ds is None or not has_datasource_access(session, current_user, ds.id):
        return _list
    tables = session.query(CoreTable).filter(
        and_(CoreTable.ds_id == ds.id, CoreTable.checked == True)
    ).all()
    tenant_id = _schema_metadata_tenant_id(session, ds, current_user)
    _apply_workspace_comments_to_tables(session, tenant_id, tables)
    conf = DatasourceConf(**json.loads(aes_decrypt(ds.configuration))) if ds.type != "excel" else get_engine_config()
    schema = effective_db_schema(ds.type, conf)

    # 获取全部字段
    table_ids = [table.id for table in tables]
    all_fields = session.query(CoreField).filter(
        and_(CoreField.table_id.in_(table_ids), CoreField.checked == True)).all()
    # 构建字典
    fields_dict = {}
    for field in all_fields:
        if fields_dict.get(field.table_id):
            fields_dict.get(field.table_id).append(field)
        else:
            fields_dict[field.table_id] = [field]

    contain_rules = get_user_permission_rules(session, current_user, ds.id)
    scoped_table_ids = get_user_scoped_table_ids(session, current_user, ds.id, contain_rules)
    if scoped_table_ids is not None:
        tables = [table for table in tables if int(table.id) in scoped_table_ids]

    for table in tables:
        # fields = session.query(CoreField).filter(and_(CoreField.table_id == table.id, CoreField.checked == True)).all()
        fields = fields_dict.get(table.id) or []
        _apply_workspace_comments_to_fields(session, tenant_id, table, fields)

        # 执行列权限过滤字段
        fields = get_column_permission_fields(session=session, current_user=current_user, table=table, fields=fields,
                                              contain_rules=contain_rules)
        _list.append(TableAndFields(schema=schema, table=table, fields=fields))
    return _list


def get_table_sample_data(session: SessionDep, current_user: CurrentUser, ds: CoreDatasource, table_name: str, fields: list) -> str:
    """
    是什么：get_table_sample_data 是一个可以复用的小步骤，负责数据源相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把数据源需要的数据找出来，整理成后面好用的样子。
    """
    if not fields:
        return ""

    db = DB.get_db(ds.type)
    # 获取标识符引用的前后缀。
    prefix = db.prefix if hasattr(db, 'prefix') else '"'
    suffix = db.suffix if hasattr(db, 'suffix') else '"'

    # 使用正确引用方式构建字段列表。
    field_names = []
    for field in fields[:10]:  # 限制为前 10 个字段，避免结果过宽。
        field_name = f"{prefix}{field.field_name}{suffix}"
        field_names.append(field_name)

    # 按数据库类型构建 LIMIT 查询。
    if equals_ignore_case(ds.type, "sqlServer"):
        query = f"SELECT TOP 3 {','.join(field_names)} FROM {prefix}{table_name}{suffix}"
    elif equals_ignore_case(ds.type, "ck"):
        query = f"SELECT {','.join(field_names)} FROM {table_name} LIMIT 3"
    elif equals_ignore_case(ds.type, "hive"):
        query = f"SELECT {','.join(field_names)} FROM {table_name} LIMIT 3"
    elif equals_ignore_case(ds.type, "oracle"):
        query = f"SELECT {','.join(field_names)} FROM \"{table_name}\" WHERE ROWNUM <= 3"
    elif equals_ignore_case(ds.type, "dm"):
        query = f"SELECT {','.join(field_names)} FROM \"{table_name}\" WHERE ROWNUM <= 3"
    else:
        query = f"SELECT {','.join(field_names)} FROM {prefix}{table_name}{suffix} LIMIT 3"

    try:
        result = execute_user_query_or_raise(
            session=session,
            current_user=current_user,
            datasource=ds,
            sql=query,
            allowed_tables=[table_name],
            origin_column=True,
            validate_columns=False,
        ).result
        if result and result.get('data') and len(result['data']) > 0:
            import json
            # 截断长字符串值以提升可读性。
            json_rows = []
            for row in result['data'][:3]:
                truncated_row = {}
                for key, value in row.items():
                    if value is None:
                        truncated_row[key] = None
                    elif isinstance(value, str):
                        # 截断长字符串
                        if len(value) > 100:
                            value = value[:100] + '...'
                        truncated_row[key] = value.replace('\n', ' ').replace('\r', ' ')
                    else:
                        truncated_row[key] = value
                json_rows.append(truncated_row)
            return json.dumps(json_rows, ensure_ascii=False, indent=2)
    except Exception:
        pass
    return ""


def get_tables_sample_data(session: SessionDep, current_user: CurrentUser, ds: CoreDatasource,
                           table_list: list[str] = None) -> str:
    """
    是什么：get_tables_sample_data 是一个可以复用的小步骤，负责数据源相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把数据源需要的数据找出来，整理成后面好用的样子。
    """
    if is_normal_user(current_user):
        return ""

    table_objs = get_table_obj_by_ds(session=session, current_user=current_user, ds=ds)
    if len(table_objs) == 0:
        return ""

    sample_data_parts = []
    for obj in table_objs:
        if table_list is not None and obj.table.table_name not in table_list:
            continue
        if obj.fields:
            sample = get_table_sample_data(session, current_user, ds, obj.table.table_name, obj.fields)
            if sample:
                sample_data_parts.append(f"# Table: {obj.table.table_name}\n{sample}")
    return "\n".join(sample_data_parts)


def _relation_id(value) -> int | None:
    """
    是什么：_relation_id 是一个可以复用的小步骤，负责数据源相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把数据源里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def get_table_schema(session: SessionDep, current_user: CurrentUser, ds: CoreDatasource, question: str,
                     embedding: bool = True, table_list: list[str] = None) -> tuple[str, list]:
    """
    是什么：get_table_schema 是一个可以复用的小步骤，负责数据源相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把数据源需要的数据找出来，整理成后面好用的样子。
    """
    schema_str = ""
    table_objs = get_table_obj_by_ds(session=session, current_user=current_user, ds=ds)
    if len(table_objs) == 0:
        return schema_str, []
    db_name = table_objs[0].schema
    schema_str += f"【DB_ID】 {db_name}\n【Schema】\n"
    tables = []
    all_tables = []  # 临时保存全部表
    table_name_list = []
    visible_table_ids = set()
    visible_field_ids = set()
    table_dict = {}
    field_dict = {}
    for obj in table_objs:
        # 如果传入了table_list，则只处理在列表中的表
        if table_list is not None and obj.table.table_name not in table_list:
            continue

        schema_table = ''
        no_schema_types = ["mysql", "es", "sqlite", "hive", "doris", "starrocks"]
        schema_table += f"# Table: {db_name}.{obj.table.table_name}" if ds.type not in no_schema_types and db_name else f"# Table: {obj.table.table_name}"
        table_comment = ''
        if obj.table.custom_comment:
            table_comment = obj.table.custom_comment.strip()
        if table_comment == '':
            schema_table += '\n[\n'
        else:
            schema_table += f", {table_comment}\n[\n"

        if obj.fields:
            field_list = []
            for field in obj.fields:
                field_comment = ''
                if field.custom_comment:
                    field_comment = field.custom_comment.strip()
                if field_comment == '':
                    field_list.append(f"({field.field_name}:{field.field_type})")
                else:
                    field_list.append(f"({field.field_name}:{field.field_type}, {field_comment})")
            schema_table += ",\n".join(field_list)
        schema_table += '\n]\n'

        table_id = int(obj.table.id)
        visible_table_ids.add(table_id)
        table_dict[table_id] = obj.table.table_name
        for field in obj.fields or []:
            field_id = int(field.id)
            visible_field_ids.add(field_id)
            field_dict[field_id] = field.field_name

        t_obj = {"id": table_id, "table_name": obj.table.table_name, "schema_table": schema_table,
                 "embedding": obj.table.embedding}
        tables.append(t_obj)
        all_tables.append(t_obj)

    # 如果没有符合过滤条件的表，直接返回
    if not tables:
        return schema_str, []

    # 执行表向量化
    if embedding and tables and settings.TABLE_EMBEDDING_ENABLED:
        missing_embedding_table_ids = [
            int(table["id"])
            for table in tables
            if not table.get("embedding")
        ]
        if missing_embedding_table_ids:
            run_save_table_embeddings(missing_embedding_table_ids, tenant_id=_schema_metadata_tenant_id(session, ds, current_user))
        tables = calc_table_embedding(tables, question)
    # 拼接结构信息
    if tables:
        for s in tables:
            schema_str += s.get('schema_table')
            table_name_list.append(s.get('table_name'))

    # 字段关系
    if tables and ds.table_relation:
        table_relation = ds.table_relation
        if isinstance(table_relation, str):
            try:
                table_relation = json.loads(table_relation)
            except Exception:
                table_relation = []
        relations = [
            relation for relation in table_relation
            if isinstance(relation, dict) and relation.get('shape') == 'edge'
        ] if isinstance(table_relation, list) else []
        if relations:
            embedding_table_ids = {int(s.get('id')) for s in tables}
            all_relations = []
            for relation in relations:
                source = relation.get('source') or {}
                target = relation.get('target') or {}
                source_table_id = _relation_id(source.get('cell'))
                source_field_id = _relation_id(source.get('port'))
                target_table_id = _relation_id(target.get('cell'))
                target_field_id = _relation_id(target.get('port'))
                if None in (source_table_id, source_field_id, target_table_id, target_field_id):
                    continue
                if source_table_id not in visible_table_ids or target_table_id not in visible_table_ids:
                    continue
                if source_field_id not in visible_field_ids or target_field_id not in visible_field_ids:
                    continue
                if source_table_id not in embedding_table_ids and target_table_id not in embedding_table_ids:
                    continue
                all_relations.append((source_table_id, source_field_id, target_table_id, target_field_id))

            # 获取缺失表 ID
            relation_table_ids = {
                table_id
                for relation in all_relations
                for table_id in (relation[0], relation[2])
            }
            lost_table_ids = list(relation_table_ids - embedding_table_ids)
            # 获取缺失表结构并拼接
            lost_tables = list(filter(lambda x: x.get('id') in lost_table_ids, all_tables))
            if lost_tables:
                for s in lost_tables:
                    schema_str += s.get('schema_table')
                    table_name_list.append(s.get('table_name'))

            if all_relations:
                schema_str += '【Foreign keys】\n'
                for source_table_id, source_field_id, target_table_id, target_field_id in all_relations:
                    schema_str += f"{table_dict.get(source_table_id)}.{field_dict.get(source_field_id)}={table_dict.get(target_table_id)}.{field_dict.get(target_field_id)}\n"

    return schema_str, table_name_list


