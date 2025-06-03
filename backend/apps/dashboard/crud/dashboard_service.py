from select import select

from apps.dashboard.models.dashboard_model import CoreDashboard
from common.core.deps import SessionDep


def get_dashboard_list(session: SessionDep):
    statement = select(CoreDashboard).order_by(CoreDashboard.create_time.desc())
    dashboard_list = session.exec(statement).fetchall()
    return dashboard_list

def preview_with_id(session: SessionDep, dashboard_id: str):
    return  session.query(CoreDashboard).filter(CoreDashboard.id == id).first()