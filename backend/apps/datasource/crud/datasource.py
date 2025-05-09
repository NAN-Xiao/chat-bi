from sqlmodel import select
from ..models.datasource import CoreDatasource, DatasourceConf
import datetime
from common.core.deps import SessionDep
import json
from ..utils.utils import aes_decrypt
from apps.db.db import get_connection

def get_datasource_list(session: SessionDep) -> CoreDatasource:
    statement = select(CoreDatasource).order_by(CoreDatasource.create_time.desc())
    datasource_list = session.exec(statement).fetchall()
    return datasource_list

def check_status(session: SessionDep, ds: CoreDatasource):
    conf = DatasourceConf(**json.loads(aes_decrypt(ds.configuration)))
    conn = get_connection(conf)
    if conn is not None:
        return True
    else:
        return False

def create_ds(session: SessionDep, ds: CoreDatasource):
    ds.create_time = datetime.datetime.now()
    ds.status = "Success"  # todo check status
    record = CoreDatasource(**ds.model_dump())
    session.add(record)
    session.commit()
    return ds

def update_ds(session: SessionDep, ds: CoreDatasource):
    ds.id = int(ds.id)
    record = session.exec(select(CoreDatasource).where(CoreDatasource.id == ds.id)).first()
    update_data = ds.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(record, field, value)
    session.add(record)
    session.commit()
    return ds

def delete_ds(session: SessionDep, id: int):
    term = session.exec(select(CoreDatasource).where(CoreDatasource.id == id)).first()
    session.delete(term)
    session.commit()
    return {
        "message": f"Datasource with ID {id} deleted successfully."
    }