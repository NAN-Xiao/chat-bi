"""
脚本说明：这个脚本封装数据源的增删改查和保存逻辑，让接口层不直接处理太多细节。
"""
import json
import time
import traceback
from typing import List

from sqlalchemy import and_, or_, select, update

from apps.ai_model.embedding import EmbeddingModelCache
from apps.system.crud.schema_metadata import SchemaFieldKey, field_comment_map, table_comment_map
from common.core.config import settings
from common.core.deps import SessionDep
from common.utils.utils import AppLogUtil
from ..models.datasource import CoreTable, CoreField, CoreDatasource


def delete_table_by_ds_id(session: SessionDep, id: int):
    """
    是什么：delete_table_by_ds_id 是一个可以复用的小步骤，负责数据源相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把数据源不再需要的数据、缓存或临时内容清理掉。
    """
    session.query(CoreTable).filter(CoreTable.ds_id == id).delete(synchronize_session=False)
    session.commit()


def get_tables_by_ds_id(session: SessionDep, id: int):
    """
    是什么：get_tables_by_ds_id 是一个可以复用的小步骤，负责数据源相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把数据源需要的数据找出来，整理成后面好用的样子。
    """
    return session.query(CoreTable).filter(CoreTable.ds_id == id).order_by(
        CoreTable.table_name.asc()).all()


def update_table(session: SessionDep, item: CoreTable):
    """
    是什么：update_table 是一个可以复用的小步骤，负责数据源相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把数据源相关的信息改成最新状态，并保存这些变化。
    """
    record = session.query(CoreTable).filter(CoreTable.id == item.id).first()
    record.checked = item.checked
    record.custom_comment = item.custom_comment
    session.add(record)
    session.commit()


def run_fill_empty_table_and_ds_embedding(session_maker, tenant_id: int | None = None):
    """
    是什么：run_fill_empty_table_and_ds_embedding 是一个可以复用的小步骤，负责数据源相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把数据源的主要流程跑起来，一步步调用需要的处理。
    """
    try:
        if not settings.TABLE_EMBEDDING_ENABLED:
            return

        session = session_maker()

        AppLogUtil.info('get tables')
        stmt = select(CoreTable.id).where(
            or_(CoreTable.embedding.is_(None), CoreTable.embedding == "")
        )
        if tenant_id is not None:
            stmt = stmt.join(CoreDatasource, CoreDatasource.id == CoreTable.ds_id).where(
                CoreDatasource.tenant_id == int(tenant_id)
            )
        results = session.execute(stmt).scalars().all()
        AppLogUtil.info('table result: ' + str(len(results)))
        save_table_embedding(session_maker, results, tenant_id=tenant_id)

        AppLogUtil.info('get datasource')
        ds_stmt = select(CoreDatasource.id).where(
            or_(CoreDatasource.embedding.is_(None), CoreDatasource.embedding == "")
        )
        if tenant_id is not None:
            ds_stmt = ds_stmt.where(CoreDatasource.tenant_id == int(tenant_id))
        ds_results = session.execute(ds_stmt).scalars().all()
        AppLogUtil.info('datasource result: ' + str(len(ds_results)))
        save_ds_embedding(session_maker, ds_results, tenant_id=tenant_id)
    except Exception:
        traceback.print_exc()
    finally:
        session_maker.remove()


def save_table_embedding(session_maker, ids: List[int], tenant_id: int | None = None):
    """
    是什么：save_table_embedding 是一个可以复用的小步骤，负责数据源相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：创建或保存数据源需要的东西，让后续流程能继续往下走。
    """
    if not settings.TABLE_EMBEDDING_ENABLED:
        return

    if not ids or len(ids) == 0:
        return
    try:
        AppLogUtil.info('start table embedding')
        start_time = time.time()
        model = EmbeddingModelCache.get_model()
        session = session_maker()
        for _id in ids:
            table_query = session.query(CoreTable).filter(CoreTable.id == _id)
            if tenant_id is not None:
                table_query = table_query.join(CoreDatasource, CoreDatasource.id == CoreTable.ds_id).filter(
                    CoreDatasource.tenant_id == int(tenant_id)
                )
            table = table_query.first()
            if table is None:
                continue
            fields = session.query(CoreField).filter(CoreField.table_id == table.id).all()
            tenant = tenant_id
            if tenant is None:
                tenant = session.execute(
                    select(CoreDatasource.tenant_id).where(CoreDatasource.id == table.ds_id)
                ).scalar()
            tenant = int(tenant) if tenant not in (None, "") else None
            table_comments = table_comment_map(session, tenant, [table.table_name])
            field_comments = field_comment_map(
                session,
                tenant,
                [SchemaFieldKey(table.table_name, field.field_name) for field in fields],
            )

            schema_table = ''
            schema_table += f"# Table: {table.table_name}"
            table_comment = (
                table_comments[table.table_name]
                if table.table_name in table_comments
                else (table.custom_comment or "").strip()
            )
            if table_comment == '':
                schema_table += '\n[\n'
            else:
                schema_table += f", {table_comment}\n[\n"

            if fields:
                field_list = []
                for field in fields:
                    field_key = (table.table_name, field.field_name)
                    field_comment = (
                        field_comments[field_key]
                        if field_key in field_comments
                        else (field.custom_comment or "").strip()
                    )
                    if field_comment == '':
                        field_list.append(f"({field.field_name}:{field.field_type})")
                    else:
                        field_list.append(f"({field.field_name}:{field.field_type}, {field_comment})")
                schema_table += ",\n".join(field_list)
            schema_table += '\n]\n'
            # table_schema.append(schema_table)
            emb = json.dumps(model.embed_query(schema_table))

            update_filters = [CoreTable.id == _id]
            if tenant_id is not None:
                allowed_ds_ids = select(CoreDatasource.id).where(CoreDatasource.tenant_id == int(tenant_id))
                update_filters.append(CoreTable.ds_id.in_(allowed_ds_ids))
            stmt = update(CoreTable).where(and_(*update_filters)).values(embedding=emb)
            session.execute(stmt)
            session.commit()

        end_time = time.time()
        AppLogUtil.info('table embedding finished in: ' + str(end_time - start_time) + ' seconds')
    except Exception:
        traceback.print_exc()
    finally:
        session_maker.remove()


def save_ds_embedding(session_maker, ids: List[int], tenant_id: int | None = None):
    """
    是什么：save_ds_embedding 是一个可以复用的小步骤，负责数据源相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：创建或保存数据源需要的东西，让后续流程能继续往下走。
    """
    if not settings.TABLE_EMBEDDING_ENABLED:
        return

    if not ids or len(ids) == 0:
        return
    try:
        AppLogUtil.info('start datasource embedding')
        start_time = time.time()
        model = EmbeddingModelCache.get_model()
        session = session_maker()
        for _id in ids:
            schema_table = ''
            ds_filters = [CoreDatasource.id == _id]
            if tenant_id is not None:
                ds_filters.append(CoreDatasource.tenant_id == int(tenant_id))
            ds = session.query(CoreDatasource).filter(and_(*ds_filters)).first()
            if ds is None:
                continue
            schema_table += f"{ds.name}, {ds.description}\n"
            tenant = int(ds.tenant_id) if getattr(ds, "tenant_id", None) not in (None, "") else None
            tables = session.query(CoreTable).filter(CoreTable.ds_id == ds.id).all()
            table_comments = table_comment_map(session, tenant, [table.table_name for table in tables])
            field_keys = []
            fields_by_table = {}
            for table in tables:
                fields = session.query(CoreField).filter(CoreField.table_id == table.id).all()
                fields_by_table[int(table.id)] = fields
                field_keys.extend(SchemaFieldKey(table.table_name, field.field_name) for field in fields)

            field_comments = field_comment_map(session, tenant, field_keys)

            for table in tables:
                fields = fields_by_table.get(int(table.id), [])
                schema_table += f"# Table: {table.table_name}"
                table_comment = (
                    table_comments[table.table_name]
                    if table.table_name in table_comments
                    else (table.custom_comment or "").strip()
                )
                if table_comment == '':
                    schema_table += '\n[\n'
                else:
                    schema_table += f", {table_comment}\n[\n"

                if fields:
                    field_list = []
                    for field in fields:
                        field_key = (table.table_name, field.field_name)
                        field_comment = (
                            field_comments[field_key]
                            if field_key in field_comments
                            else (field.custom_comment or "").strip()
                        )
                        if field_comment == '':
                            field_list.append(f"({field.field_name}:{field.field_type})")
                        else:
                            field_list.append(f"({field.field_name}:{field.field_type}, {field_comment})")
                    schema_table += ",\n".join(field_list)
                schema_table += '\n]\n'
            # table_schema.append(schema_table)
            emb = json.dumps(model.embed_query(schema_table))

            update_filters = [CoreDatasource.id == _id]
            if tenant_id is not None:
                update_filters.append(CoreDatasource.tenant_id == int(tenant_id))
            stmt = update(CoreDatasource).where(and_(*update_filters)).values(embedding=emb)
            session.execute(stmt)
            session.commit()

        end_time = time.time()
        AppLogUtil.info('datasource embedding finished in: ' + str(end_time - start_time) + ' seconds')
    except Exception:
        traceback.print_exc()
    finally:
        session_maker.remove()
