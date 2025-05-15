from common.core.deps import SessionDep
from ..models.datasource import CoreDatasource, CreateDatasource, CoreTable, CoreField, ColumnSchema


def delete_field_by_ds_id(session: SessionDep, id: int):
    session.query(CoreField).filter(CoreField.ds_id == id).delete(synchronize_session=False)
    session.commit()
