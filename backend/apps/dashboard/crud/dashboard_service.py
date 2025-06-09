from sqlalchemy import select, and_, text
from apps.dashboard.models.dashboard_model import CoreDashboard, CreateDashboard, QueryDashboard
from common.core.deps import SessionDep, CurrentUser
import uuid
import datetime
def get_dashboard_list(session: SessionDep,dashboard: QueryDashboard):
    sql = text("SELECT id, name, type,node_type, pid, create_time FROM core_dashboard")
    for row in session.exec(sql).mappings():
        yield CoreDashboard(**row)

def preview_with_id(session: SessionDep, dashboard_id: str):
    return  session.query(CoreDashboard).filter(CoreDashboard.id == id).first()

def get_create_base_info(user: CurrentUser, dashboard: CreateDashboard):
    new_id = uuid.uuid4().hex
    record = CoreDashboard(**dashboard.model_dump())
    record.id = new_id
    record.create_by = user.id
    return record

def create_resource(session: SessionDep, user: CurrentUser, dashboard: CreateDashboard):
    record = get_create_base_info(user, dashboard)
    session.add(record)
    session.flush()
    session.refresh(record)
    session.commit()
    return record

def update_resource(session: SessionDep, user: CurrentUser, dashboard: CreateDashboard):
    record = session.query(CoreDashboard).filter(CoreDashboard.id == dashboard.id).first()
    record.name = dashboard.name
    record.update_by = user.id
    record.update_time = datetime.datetime.now()
    session.add(record)
    session.commit()

def create_canvas(session: SessionDep, user: CurrentUser, dashboard: CreateDashboard):
    record = get_create_base_info(user, dashboard)
    record.node_type = dashboard.node_type
    record.component_data = dashboard.component_data
    record.canvas_style_data = dashboard.canvas_style_data
    session.add(record)
    session.flush()
    return record

def update_canvas(session: SessionDep, user: CurrentUser, dashboard: CreateDashboard):
    record = session.query(CoreDashboard).filter(CoreDashboard.id == dashboard.id).first()


def validate_name( session: SessionDep, dashboard: QueryDashboard) -> bool:
    if not dashboard.workspace_id:
        raise ValueError("workspace_id is required")
    if not dashboard.pid:
        raise ValueError("pid is required")
    if not dashboard.opt:
        raise ValueError("opt is required")

    if dashboard.opt in ('newLeaf', 'newFolder'):
        query = session.query(CoreDashboard).filter(
            and_(
                CoreDashboard.workspace_id == dashboard.workspace_id,
                CoreDashboard.pid == dashboard.pid,
                CoreDashboard.name == dashboard.name
            )
        )
    elif dashboard.opt in ('updateLeaf', 'updateFolder'):
        if not dashboard.id:
            raise ValueError("id is required for update operation")
        query = session.query(CoreDashboard).filter(
            and_(
                CoreDashboard.workspace_id == dashboard.workspace_id,
                CoreDashboard.pid == dashboard.pid,
                CoreDashboard.name == dashboard.name,
                CoreDashboard.id != dashboard.id
            )
        )
    else:
        raise ValueError(f"Invalid opt value: {dashboard.opt}")
    return not session.query(query.exists()).scalar()