from sqlmodel import select
from ..models.datasource import CoreDatasource, DatasourceConf
import datetime
from common.core.deps import SessionDep
from apps.db.db import get_session, get_tables, get_fields, exec_sql
from sqlalchemy import text


def get_datasource_list(session: SessionDep) -> CoreDatasource:
    statement = select(CoreDatasource).order_by(CoreDatasource.create_time.desc())
    datasource_list = session.exec(statement).fetchall()
    return datasource_list


def check_status(session: SessionDep, ds: CoreDatasource):
    conn = get_session(ds)
    try:
        conn.execute(text("SELECT 1")).scalar()
        print("success")
        return True
    except Exception as e:
        print("Fail:", e)
        return False
    finally:
        conn.close()
    return False


def create_ds(session: SessionDep, ds: CoreDatasource):
    ds.create_time = datetime.datetime.now()
    status = check_status(session, ds)
    ds.status = "Success" if status is True else "Fail"
    record = CoreDatasource(**ds.model_dump())
    # get tables and fields
    if status:
        pass
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


def getTables(session: SessionDep, id: int):
    ds = session.exec(select(CoreDatasource).where(CoreDatasource.id == id)).first()
    tables = get_tables(ds)
    return tables


def getFields(session: SessionDep, id: int, table_name: str):
    ds = session.exec(select(CoreDatasource).where(CoreDatasource.id == id)).first()
    fields = get_fields(ds, table_name)
    return fields


def execSql(session: SessionDep, id: int, sql: str):
    ds = session.exec(select(CoreDatasource).where(CoreDatasource.id == id)).first()
    return exec_sql(ds, sql)
