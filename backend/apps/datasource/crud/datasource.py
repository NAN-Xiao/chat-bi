from sqlmodel import select
from ..models.datasource import CoreDatasource, DatasourceConf
import pyodbc
import datetime
from common.core.deps import SessionDep

def get_datasource_list(session: SessionDep) -> CoreDatasource:
    statement = select(CoreDatasource).order_by(CoreDatasource.create_time.desc())
    datasource_list = session.exec(statement).fetchall()
    return datasource_list

def check_status(session: SessionDep, conf: DatasourceConf):
    conn_str = (
        "DRIVER={MySQL ODBC 9.3 Unicode Driver};" # todo driver config
        f"SERVER={conf.host};"
        f"DATABASE={conf.database};"
        f"UID={conf.username};"
        f"PWD={conf.password};"
        f"PORT={conf.port};"
    )

    conn = None
    try:
        conn = pyodbc.connect(conn_str)
        print("Connect Success")
        return True
    except pyodbc.Error as e:
        print(f"Connect Fail：{e}")
        return False
    finally:
        if conn is not None:
            conn.close()

def create_ds(session: SessionDep, ds: CoreDatasource):
    record = CoreDatasource(**ds.model_dump())
    record.create_time = datetime.datetime.now()
    record.status = "Success" # todo check status
    session.add(record)
    session.commit()
    return record

def update_ds(session: SessionDep, ds: CoreDatasource):
    ds.id = int(ds.id)
    term = session.exec(select(CoreDatasource).where(CoreDatasource.id == ds.id)).first()
    update_data = ds.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(term, field, value)
    session.add(term)
    session.commit()
    return ds

def delete_ds(session: SessionDep, id: int):
    term = session.exec(select(CoreDatasource).where(CoreDatasource.id == id)).first()
    session.delete(term)
    session.commit()
    return {
        "message": f"Datasource with ID {id} deleted successfully."
    }