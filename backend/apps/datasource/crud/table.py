import json
import time
import traceback
from typing import List

from sqlalchemy import and_, select, update

from apps.ai_model.embedding import EmbeddingModelCache
from common.core.config import settings
from common.core.deps import SessionDep
from common.utils.utils import AppLogUtil
from ..models.datasource import CoreTable, CoreField, CoreDatasource


def delete_table_by_ds_id(session: SessionDep, id: int):
    session.query(CoreTable).filter(CoreTable.ds_id == id).delete(synchronize_session=False)
    session.commit()


def get_tables_by_ds_id(session: SessionDep, id: int):
    return session.query(CoreTable).filter(CoreTable.ds_id == id).order_by(
        CoreTable.table_name.asc()).all()


def update_table(session: SessionDep, item: CoreTable):
    record = session.query(CoreTable).filter(CoreTable.id == item.id).first()
    record.checked = item.checked
    record.custom_comment = item.custom_comment
    session.add(record)
    session.commit()


def run_fill_empty_table_and_ds_embedding(session_maker, tenant_id: int | None = None):
    try:
        if not settings.TABLE_EMBEDDING_ENABLED:
            return

        session = session_maker()

        AppLogUtil.info('get tables')
        stmt = select(CoreTable.id).where(and_(CoreTable.embedding.is_(None)))
        if tenant_id is not None:
            stmt = stmt.join(CoreDatasource, CoreDatasource.id == CoreTable.ds_id).where(
                CoreDatasource.tenant_id == int(tenant_id)
            )
        results = session.execute(stmt).scalars().all()
        AppLogUtil.info('table result: ' + str(len(results)))
        save_table_embedding(session_maker, results, tenant_id=tenant_id)

        AppLogUtil.info('get datasource')
        ds_stmt = select(CoreDatasource.id).where(and_(CoreDatasource.embedding.is_(None)))
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

            schema_table = ''
            schema_table += f"# Table: {table.table_name}"
            table_comment = ''
            if table.custom_comment:
                table_comment = table.custom_comment.strip()
            if table_comment == '':
                schema_table += '\n[\n'
            else:
                schema_table += f", {table_comment}\n[\n"

            if fields:
                field_list = []
                for field in fields:
                    field_comment = ''
                    if field.custom_comment:
                        field_comment = field.custom_comment.strip()
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
            tables = session.query(CoreTable).filter(CoreTable.ds_id == ds.id).all()
            for table in tables:
                fields = session.query(CoreField).filter(CoreField.table_id == table.id).all()

                schema_table += f"# Table: {table.table_name}"
                table_comment = ''
                if table.custom_comment:
                    table_comment = table.custom_comment.strip()
                if table_comment == '':
                    schema_table += '\n[\n'
                else:
                    schema_table += f", {table_comment}\n[\n"

                if fields:
                    field_list = []
                    for field in fields:
                        field_comment = ''
                        if field.custom_comment:
                            field_comment = field.custom_comment.strip()
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
