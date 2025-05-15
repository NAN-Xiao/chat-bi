from common.core.deps import SessionDep
from ..models.datasource import CoreDatasource, CreateDatasource, CoreTable, CoreField, ColumnSchema


def delete_table_by_ds_id(session: SessionDep, id: int):
    session.query(CoreTable).filter(CoreTable.ds_id == id).delete(synchronize_session=False)
    session.commit()
