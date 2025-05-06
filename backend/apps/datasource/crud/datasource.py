from sqlmodel import Session, select
from ..models.datasource import CoreDatasource, DatasourceConf
import pyodbc
import datetime

def get_datasource_list(session: Session) -> CoreDatasource:
    statement = select(CoreDatasource)
    datasource_list = session.exec(statement).fetchall()
    return datasource_list

def check_status(session: Session, conf: DatasourceConf):
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

def create_ds(session: Session, ds: CoreDatasource):
    record = CoreDatasource(**ds.model_dump())
    record.create_time = datetime.datetime.now()
    record.status = "Success" # todo check status
    session.add(record)
    session.commit()
    return record