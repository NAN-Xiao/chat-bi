from common.core.deps import SessionDep
from ..models.datasource import CoreDatasource, CreateDatasource, CoreTable, CoreField, ColumnSchema
from sqlalchemy import and_


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
