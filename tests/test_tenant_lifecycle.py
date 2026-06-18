import pytest
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, create_engine

from apps.system.crud.tenant import DEFAULT_TENANT_ID, delete_tenant, list_tenants, set_tenant_status
from apps.system.models.tenant import TenantModel


def _engine():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TenantModel.__table__.create(engine)
    return engine


def test_tenant_must_be_disabled_before_soft_delete():
    engine = _engine()
    with Session(engine) as session:
        session.add(TenantModel(id=10, code="tenant-a", name="Tenant A", status=1))
        session.commit()

        with pytest.raises(ValueError, match="disabled"):
            delete_tenant(session, tenant_id=10)

        set_tenant_status(session, tenant_id=10, status=0)
        deleted = delete_tenant(session, tenant_id=10)
        session.commit()

        assert deleted.status == -1
        assert list_tenants(session, include_disabled=True) == []


def test_default_tenant_cannot_be_deleted():
    engine = _engine()
    with Session(engine) as session:
        session.add(
            TenantModel(
                id=DEFAULT_TENANT_ID,
                code="default",
                name="Default",
                status=0,
            )
        )
        session.commit()

        with pytest.raises(ValueError, match="Default tenant cannot be deleted"):
            delete_tenant(session, tenant_id=DEFAULT_TENANT_ID)
