from sqlmodel import Session, select
from ..models.datasource import core_datasource

def get_datasource_list(session: Session) -> core_datasource | None:
    statement = select(core_datasource)
    datasource_list = session.exec(statement).fetchall()
    return datasource_list