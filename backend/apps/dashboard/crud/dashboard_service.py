from sqlalchemy import select
from apps.dashboard.models.dashboard_model import CoreDashboard, CreateDashboard
from common.core.deps import SessionDep, CurrentUser
from sqlmodel import text
import uuid
def get_dashboard_list(session: SessionDep):
    sql = text("SELECT id, name, type,node_type, pid, create_time FROM core_dashboard")
    for row in session.exec(sql).mappings():
        yield CoreDashboard(**row)

def preview_with_id(session: SessionDep, dashboard_id: str):
    return  session.query(CoreDashboard).filter(CoreDashboard.id == id).first()


def create_dashboard(session: SessionDep, user: CurrentUser, dashboard: CreateDashboard):
    new_id = uuid.uuid4().hex
    record = CoreDashboard(**dashboard.model_dump())
    record.id = new_id
    record.create_by = user.id
    session.add(record)
    session.flush()
    session.refresh(record)
    session.commit()
    return record
