import json
import time
import traceback
from typing import List

from sqlalchemy import and_, select, update

from apps.ai_model.embedding import EmbeddingModelCache
from common.core.config import settings
from common.core.deps import SessionDep
from common.utils.utils import SQLBotLogUtil
from ..models.datasource import CoreTable, CoreField


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


def run_fill_empty_table_embedding(session: SessionDep):
    if not settings.EMBEDDING_ENABLED:
        return

    stmt = select(CoreTable.id).where(and_(CoreTable.embedding.is_(None)))
    results = session.execute(stmt).scalars().all()
    SQLBotLogUtil.info(json.dumps(results))

    save_table_embedding(session, results)


def save_table_embedding(session: SessionDep, ids: List[int]):
    if not settings.EMBEDDING_ENABLED:
        return

    if not ids or len(ids) == 0:
        return
    try:

        _list = session.query(CoreTable).filter(and_(CoreTable.id.in_(ids))).all()

        table_schema = []
        for item in _list:
            fields = session.query(CoreField).filter(CoreField.table_id == item.id).all()

            schema_table = ''
            schema_table += f"# Table: {item.table_name}"
            table_comment = ''
            if item.custom_comment:
                table_comment = item.custom_comment.strip()
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
            table_schema.append(schema_table)

        model = EmbeddingModelCache.get_model()

        SQLBotLogUtil.info(json.dumps(table_schema))
        SQLBotLogUtil.info('start table embedding')
        start_time = time.time()
        results = model.embed_documents(table_schema)
        end_time = time.time()
        SQLBotLogUtil.info('table embedding finished in:' + str(end_time - start_time) + 'seconds')

        for index in range(len(results)):
            item = results[index]
            stmt = update(CoreTable).where(and_(CoreTable.id == _list[index].id)).values(embedding=item)
            session.execute(stmt)
            session.commit()

    except Exception:
        traceback.print_exc()
