import asyncio
import json
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, create_engine, select

from apps.system.crud.tenant import (
    DEFAULT_TENANT_CODE,
    DEFAULT_TENANT_ID,
    TENANT_APPLICATION_TYPE_INVITE,
    TENANT_APPLICATION_TYPE_JOIN,
    TENANT_ROLE_ADMIN,
    TENANT_ROLE_MEMBER,
    auto_assign_tenants_by_email_domain,
    create_tenant_invitation,
    assign_user_to_tenant,
    ensure_default_tenant,
    resolve_current_tenant,
    validate_tenant_security_policy,
    user_belongs_to_tenant,
)
from apps.system.api import tenant as tenant_api
from apps.system.models.tenant import (
    TenantApplicationModel,
    TenantDataRequestModel,
    TenantDomainModel,
    TenantModel,
    TenantSecurityPolicyModel,
    TenantUserModel,
)
from apps.system.schemas.system_schema import BaseUserDTO
from apps.system.schemas.tenant_schema import (
    TenantApplicationCreator,
    TenantApplicationReview,
    TenantBulkInviteCreator,
    TenantDataRequestComplete,
    TenantDataRequestCreator,
    TenantDataRequestReview,
    TenantDomainCreator,
    TenantDomainReview,
    TenantSecurityPolicyEditor,
    TenantEditor,
    TenantOwnerTransfer,
    TenantStatus,
)
from common.audit.models.log_model import SystemLog


def _engine():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TenantModel.__table__.create(engine)
    TenantUserModel.__table__.create(engine)
    TenantApplicationModel.__table__.create(engine)
    TenantDomainModel.__table__.create(engine)
    TenantSecurityPolicyModel.__table__.create(engine)
    TenantDataRequestModel.__table__.create(engine)
    SystemLog.__table__.create(engine)
    with engine.begin() as conn:
        conn.execute(text(
            """
            CREATE TABLE sys_user (
                id INTEGER PRIMARY KEY,
                account VARCHAR(255) NOT NULL UNIQUE,
                name VARCHAR(255) NOT NULL UNIQUE,
                password VARCHAR(255) NOT NULL,
                email VARCHAR(255),
                status INTEGER NOT NULL,
                origin INTEGER NOT NULL DEFAULT 0,
                create_time INTEGER NOT NULL,
                language VARCHAR(255),
                system_role VARCHAR(32) NOT NULL DEFAULT 'viewer',
                system_variables TEXT
            )
            """
        ))
        conn.execute(text(
            """
            CREATE TABLE core_datasource (
                id INTEGER PRIMARY KEY,
                tenant_id INTEGER NOT NULL DEFAULT 1,
                name VARCHAR(128) NOT NULL
            )
            """
        ))
        conn.execute(text(
            """
            CREATE TABLE core_datasource_user (
                id INTEGER PRIMARY KEY,
                ds_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL
            )
            """
        ))
        conn.execute(text(
            """
            CREATE TABLE tenant_export_rows (
                id INTEGER PRIMARY KEY,
                tenant_id INTEGER NOT NULL,
                value VARCHAR(32)
            )
            """
        ))
    return engine


def _user(user_id: int, role: str = "viewer"):
    return SimpleNamespace(id=user_id, system_role=role)


def test_default_tenant_is_created_once():
    engine = _engine()
    with Session(engine) as session:
        first = ensure_default_tenant(session)
        second = ensure_default_tenant(session)

        assert first.id == DEFAULT_TENANT_ID
        assert first.code == DEFAULT_TENANT_CODE
        assert second.id == first.id


def test_user_without_membership_has_no_current_tenant():
    engine = _engine()
    with Session(engine) as session:
        tenant = resolve_current_tenant(session, _user(100))

        assert tenant is None
        assert not user_belongs_to_tenant(session, 100, DEFAULT_TENANT_ID)


def test_regular_user_default_tenant_header_does_not_create_membership():
    engine = _engine()
    with Session(engine) as session:
        tenant = resolve_current_tenant(
            session,
            _user(100),
            requested_tenant_id=DEFAULT_TENANT_ID,
        )

        assert tenant is None
        assert not user_belongs_to_tenant(session, 100, DEFAULT_TENANT_ID)


def test_user_cannot_resolve_another_tenant_without_membership():
    engine = _engine()
    with Session(engine) as session:
        session.add(TenantModel(id=200, code="tenant-b", name="Tenant B", status=1, plan="default"))
        session.commit()

        with pytest.raises(PermissionError):
            resolve_current_tenant(session, _user(100), requested_tenant_id=200)


def test_user_can_resolve_requested_tenant_when_member():
    engine = _engine()
    with Session(engine) as session:
        session.add(TenantModel(id=200, code="tenant-b", name="Tenant B", status=1, plan="default"))
        session.flush()
        assign_user_to_tenant(session, 100, tenant_id=200, role=TENANT_ROLE_ADMIN, is_primary=True)

        tenant = resolve_current_tenant(session, _user(100), requested_tenant_id=200)

        assert tenant.id == 200
        assert tenant.role == TENANT_ROLE_ADMIN


def test_system_admin_can_resolve_active_tenant_for_platform_operations():
    engine = _engine()
    with Session(engine) as session:
        session.add(TenantModel(id=200, code="tenant-b", name="Tenant B", status=1, plan="default"))
        session.commit()

        tenant = resolve_current_tenant(session, _user(1, "system_admin"), requested_tenant_id=200)

        assert tenant.id == 200
        assert tenant.role == "owner"


def test_user_token_payload_includes_current_tenant():
    user = BaseUserDTO(
        id=100,
        account="demo",
        name="Demo",
        email="demo@example.com",
        password="secret",
        status=1,
        origin=0,
        system_role="viewer",
        tenant_id=DEFAULT_TENANT_ID,
    )

    assert user.to_dict() == {
        "id": 100,
        "account": "demo",
        "tenant_id": DEFAULT_TENANT_ID,
    }


def test_platform_admin_lists_all_active_tenants():
    engine = _engine()
    with Session(engine) as session:
        session.add(TenantModel(id=200, code="tenant-b", name="Tenant B", status=1, plan="default"))
        session.add(TenantModel(id=300, code="tenant-c", name="Tenant C", status=0, plan="default"))
        session.commit()

        tenants = asyncio.run(tenant_api.tenant_list(session, _user(1, "system_admin")))

        assert {tenant.code for tenant in tenants} == {"tenant-b"}
        assert all(tenant.role == "owner" for tenant in tenants)


def test_tenant_member_list_hides_operations_fields():
    engine = _engine()
    with Session(engine) as session:
        session.add(
            TenantModel(
                id=200,
                code="tenant-b",
                name="Tenant B",
                status=1,
                plan="enterprise",
                billing_mode="contract",
                contract_no="CTR-001",
                billing_contact="Ops",
                billing_email="ops@example.com",
                subscription_note="internal",
            )
        )
        session.add(TenantUserModel(id=201, tenant_id=200, user_id=100, role="member", is_primary=True, status=1))
        session.add(TenantUserModel(id=202, tenant_id=200, user_id=101, role="owner", is_primary=True, status=1))
        session.commit()

        tenants = asyncio.run(tenant_api.tenant_list(session, _user(100)))

        assert len(tenants) == 1
        tenant = tenants[0]
        assert tenant.code == "tenant-b"
        assert tenant.role == "member"
        assert tenant.plan is None
        assert tenant.billing_mode is None
        assert tenant.contract_no is None
        assert tenant.billing_contact is None
        assert tenant.billing_email is None
        assert tenant.subscription_note is None
        assert tenant.owner_user_id is None


def test_only_platform_admin_can_use_tenant_admin_list():
    engine = _engine()
    with Session(engine) as session:
        session.add(TenantModel(id=200, code="tenant-b", name="Tenant B", status=1, plan="default"))
        session.commit()

        with pytest.raises(HTTPException) as exc:
            asyncio.run(tenant_api.admin_tenant_list(session, _user(100)))

        assert exc.value.status_code == 403


def test_platform_admin_manages_tenant_lifecycle():
    engine = _engine()
    with Session(engine) as session:
        tenant = asyncio.run(tenant_api.add_tenant(
            session,
            _user(1, "system_admin"),
            tenant_api.TenantCreator(
                code="tenant-b",
                name="Tenant B",
                plan="basic",
                subscription_status="trialing",
                billing_mode="contract",
                trial_end_time=1000,
                current_period_end_time=2000,
                contract_no="CTR-001",
                billing_contact="Ops",
                billing_email="ops@example.com",
                subscription_note="pilot",
            ),
        ))
        assert tenant.code == "tenant-b"
        assert tenant.plan == "basic"
        assert tenant.subscription_status == "trialing"
        assert tenant.billing_mode == "contract"
        assert tenant.current_period_end_time == 2000
        assert tenant.contract_no == "CTR-001"
        assert tenant.status == 1

        edited = asyncio.run(tenant_api.edit_tenant(
            session,
            _user(1, "system_admin"),
            tenant.id,
            TenantEditor(
                name="Tenant Beta",
                plan="enterprise",
                subscription_status="past_due",
                billing_mode="manual",
                trial_end_time=None,
                current_period_end_time=3000,
                contract_no="CTR-002",
                billing_contact="Finance",
                billing_email="finance@example.com",
                subscription_note="manual follow-up required",
            ),
        ))
        assert edited.name == "Tenant Beta"
        assert edited.plan == "enterprise"
        assert edited.subscription_status == "past_due"
        assert edited.current_period_end_time == 3000
        assert edited.subscription_note == "manual follow-up required"

        disabled = asyncio.run(tenant_api.update_tenant_status(
            session,
            _user(1, "system_admin"),
            tenant.id,
            TenantStatus(status=0),
        ))
        assert disabled.status == 0

        admin_rows = asyncio.run(tenant_api.admin_tenant_list(session, _user(1, "system_admin")))
        assert {row.code for row in admin_rows} == {"tenant-b"}


def test_default_tenant_cannot_be_disabled():
    engine = _engine()
    with Session(engine) as session:
        ensure_default_tenant(session)
        session.commit()

        with pytest.raises(HTTPException) as exc:
            asyncio.run(tenant_api.update_tenant_status(
                session,
                _user(1, "system_admin"),
                DEFAULT_TENANT_ID,
                TenantStatus(status=0),
            ))

        assert exc.value.status_code == 400


def test_user_submits_tenant_application_and_platform_admin_approves_workspace():
    engine = _engine()
    applicant = _user(100)
    platform_admin = _user(1, "system_admin")
    with Session(engine) as session:
        application = asyncio.run(tenant_api.submit_tenant_application(
            session,
            applicant,
            TenantApplicationCreator(
                tenant_name="Tenant B",
                plan="enterprise",
                requested_role="owner",
                reason="Need a company workspace",
            ),
        ))

        assert application.status == "pending"
        assert application.applicant_user_id == 100
        assert application.tenant_code == ""

        reviewed = asyncio.run(tenant_api.review_tenant_application(
            session,
            platform_admin,
            int(application.id),
            TenantApplicationReview(approved=True, tenant_code="tenant-b", review_comment="ok"),
        ))

        assert reviewed.status == "approved"
        assert reviewed.tenant_id is not None
        assert reviewed.tenant_code == "tenant-b"
        assert user_belongs_to_tenant(session, 100, int(reviewed.tenant_id))
        membership = session.exec(
            select(TenantUserModel).where(
                TenantUserModel.tenant_id == int(reviewed.tenant_id),
                TenantUserModel.user_id == 100,
            )
        ).one()
        assert membership.role == "owner"
        audit_log = session.exec(
            select(SystemLog).where(
                SystemLog.tenant_id == int(reviewed.tenant_id),
                SystemLog.operation_detail == "审核企业创建申请通过",
            )
        ).first()
        assert audit_log is not None
        assert audit_log.resource_id == str(application.id)
        assert audit_log.resource_name == "Tenant B"


def test_rejected_tenant_application_does_not_create_workspace():
    engine = _engine()
    applicant = _user(100)
    platform_admin = _user(1, "system_admin")
    with Session(engine) as session:
        application = asyncio.run(tenant_api.submit_tenant_application(
            session,
            applicant,
            TenantApplicationCreator(
                tenant_name="Tenant B",
                requested_role="admin",
            ),
        ))

        reviewed = asyncio.run(tenant_api.review_tenant_application(
            session,
            platform_admin,
            int(application.id),
            TenantApplicationReview(approved=False, review_comment="missing proof"),
        ))

        assert reviewed.status == "rejected"
        assert session.exec(select(TenantModel).where(TenantModel.code == "tenant-b")).first() is None
        assert not user_belongs_to_tenant(session, 100, 200)


def test_create_tenant_application_always_grants_owner_role():
    engine = _engine()
    applicant = _user(100)
    platform_admin = _user(1, "system_admin")
    with Session(engine) as session:
        application = asyncio.run(tenant_api.submit_tenant_application(
            session,
            applicant,
            TenantApplicationCreator(
                tenant_name="Tenant B",
                requested_role="admin",
            ),
        ))

        assert application.requested_role == "owner"

        reviewed = asyncio.run(tenant_api.review_tenant_application(
            session,
            platform_admin,
            int(application.id),
            TenantApplicationReview(approved=True, tenant_code="tenant-b", review_comment="ok"),
        ))

        membership = session.exec(
            select(TenantUserModel).where(
                TenantUserModel.tenant_id == int(reviewed.tenant_id),
                TenantUserModel.user_id == 100,
            )
        ).one()
        assert membership.role == "owner"


def test_create_tenant_application_approval_requires_platform_assigned_code():
    engine = _engine()
    applicant = _user(100)
    platform_admin = _user(1, "system_admin")
    with Session(engine) as session:
        application = asyncio.run(tenant_api.submit_tenant_application(
            session,
            applicant,
            TenantApplicationCreator(
                tenant_name="Tenant B",
                requested_role="owner",
            ),
        ))

        with pytest.raises(HTTPException) as exc:
            asyncio.run(tenant_api.review_tenant_application(
                session,
                platform_admin,
                int(application.id),
                TenantApplicationReview(approved=True, review_comment="ok"),
            ))

        assert exc.value.status_code == 400
        assert "Tenant code is required" in str(exc.value.detail)


def test_create_tenant_application_rejects_existing_tenant_name():
    engine = _engine()
    applicant = _user(100)
    with Session(engine) as session:
        session.add(TenantModel(id=200, code="tenant-b", name="Tenant B", status=1, plan="basic"))
        session.commit()

        with pytest.raises(HTTPException) as exc:
            asyncio.run(tenant_api.submit_tenant_application(
                session,
                applicant,
                TenantApplicationCreator(
                    tenant_name="Tenant B",
                    requested_role="owner",
                ),
            ))

        assert exc.value.status_code == 400
        assert "Tenant name already exists" in str(exc.value.detail)


def test_create_tenant_application_rejects_pending_duplicate_name():
    engine = _engine()
    first_applicant = _user(100)
    second_applicant = _user(101)
    with Session(engine) as session:
        asyncio.run(tenant_api.submit_tenant_application(
            session,
            first_applicant,
            TenantApplicationCreator(
                tenant_name="Tenant B",
                requested_role="owner",
            ),
        ))

        with pytest.raises(HTTPException) as exc:
            asyncio.run(tenant_api.submit_tenant_application(
                session,
                second_applicant,
                TenantApplicationCreator(
                    tenant_name="Tenant B",
                    requested_role="owner",
                ),
            ))

        assert exc.value.status_code == 400
        assert "Tenant application for this name is already pending" in str(exc.value.detail)


def test_user_searches_tenant_and_applies_to_join_by_id():
    engine = _engine()
    applicant = _user(100)
    tenant_admin = SimpleNamespace(id=2, system_role="viewer", tenant_id=200, tenant_role="admin")
    current_tenant = SimpleNamespace(id=200, code="tenant-b", name="Tenant B", role="admin")
    with Session(engine) as session:
        session.add(TenantModel(id=200, code="tenant-b", name="Tenant B", status=1, plan="basic"))
        session.commit()

        search_rows = asyncio.run(tenant_api.search_tenants(session, applicant, keyword="200"))
        assert len(search_rows) == 1
        assert search_rows[0].id == 200
        assert search_rows[0].already_joined is False

        application = asyncio.run(tenant_api.submit_tenant_application(
            session,
            applicant,
            TenantApplicationCreator(
                application_type=TENANT_APPLICATION_TYPE_JOIN,
                tenant_id=200,
                requested_role="admin",
                reason="Please add me",
            ),
        ))
        assert application.application_type == "join"
        assert application.tenant_id == 200
        assert application.requested_role == "member"

        reviewed = asyncio.run(tenant_api.review_tenant_join_application(
            session,
            tenant_admin,
            current_tenant,
            int(application.id),
            TenantApplicationReview(approved=True, review_comment="ok"),
        ))

        assert reviewed.status == "approved"
        assert user_belongs_to_tenant(session, 100, 200)
        membership = session.exec(
            select(TenantUserModel).where(
                TenantUserModel.tenant_id == 200,
                TenantUserModel.user_id == 100,
            )
        ).one()
        assert membership.role == "member"


def test_legacy_join_application_requesting_admin_is_approved_as_member():
    engine = _engine()
    tenant_admin = SimpleNamespace(id=2, system_role="viewer", tenant_id=200, tenant_role="admin")
    current_tenant = SimpleNamespace(id=200, code="tenant-b", name="Tenant B", role="admin")
    with Session(engine) as session:
        session.add(TenantModel(id=200, code="tenant-b", name="Tenant B", status=1, plan="basic"))
        application = TenantApplicationModel(
            application_type=TENANT_APPLICATION_TYPE_JOIN,
            applicant_user_id=100,
            tenant_id=200,
            tenant_code="tenant-b",
            tenant_name="Tenant B",
            plan="basic",
            requested_role="admin",
            status="pending",
        )
        session.add(application)
        session.commit()

        reviewed = asyncio.run(tenant_api.review_tenant_join_application(
            session,
            tenant_admin,
            current_tenant,
            int(application.id),
            TenantApplicationReview(approved=True, review_comment="ok"),
        ))

        assert reviewed.status == "approved"
        membership = session.exec(
            select(TenantUserModel).where(
                TenantUserModel.tenant_id == 200,
                TenantUserModel.user_id == 100,
            )
        ).one()
        assert membership.role == "member"


def test_tenant_join_search_does_not_fuzzy_disclose_tenant_names_or_codes():
    engine = _engine()
    applicant = _user(100)
    with Session(engine) as session:
        session.add(TenantModel(id=200, code="tenant-b", name="Tenant Beta", status=1, plan="basic"))
        session.add(TenantModel(id=300, code="finance-prod", name="Finance Production", status=1, plan="basic"))
        session.commit()

        by_code = asyncio.run(tenant_api.search_tenants(session, applicant, keyword="tenant-b"))
        by_id = asyncio.run(tenant_api.search_tenants(session, applicant, keyword="300"))
        by_name = asyncio.run(tenant_api.search_tenants(session, applicant, keyword="Finance"))
        by_partial_code = asyncio.run(tenant_api.search_tenants(session, applicant, keyword="tenant"))

        assert [row.id for row in by_code] == [200]
        assert [row.id for row in by_id] == [300]
        assert by_name == []
        assert by_partial_code == []


def test_pending_join_application_can_be_cancelled_by_applicant():
    engine = _engine()
    applicant = _user(100)
    with Session(engine) as session:
        session.add(TenantModel(id=200, code="tenant-b", name="Tenant B", status=1, plan="basic"))
        session.commit()

        application = asyncio.run(tenant_api.submit_tenant_application(
            session,
            applicant,
            TenantApplicationCreator(
                application_type=TENANT_APPLICATION_TYPE_JOIN,
                tenant_id=200,
                requested_role="member",
            ),
        ))

        cancelled = asyncio.run(tenant_api.cancel_my_tenant_application(
            session,
            applicant,
            int(application.id),
        ))

        assert cancelled.status == "cancelled"
        assert not user_belongs_to_tenant(session, 100, 200)


def test_tenant_admin_invites_existing_user_and_user_accepts():
    engine = _engine()
    tenant_admin = SimpleNamespace(id=2, system_role="viewer", tenant_id=200, tenant_role="admin")
    invitee = _user(100)
    current_tenant = SimpleNamespace(id=200, code="tenant-b", name="Tenant B", role="admin")
    with Session(engine) as session:
        session.add(TenantModel(id=200, code="tenant-b", name="Tenant B", status=1, plan="basic"))
        session.add(TenantUserModel(id=201, tenant_id=200, user_id=2, role="admin", is_primary=True, status=1))
        invitation = create_tenant_invitation(
            session,
            tenant_id=200,
            invitee_user_id=100,
            invited_by_user_id=2,
            requested_role="member",
        )
        session.commit()

        invited_rows = asyncio.run(tenant_api.my_tenant_invitations(session, invitee))
        assert [row.id for row in invited_rows] == [invitation.id]
        assert invited_rows[0].application_type == TENANT_APPLICATION_TYPE_INVITE

        accepted = asyncio.run(tenant_api.respond_tenant_invitation(
            session,
            invitee,
            int(invitation.id),
            TenantApplicationReview(approved=True, review_comment="accepted"),
        ))

        assert accepted.status == "approved"
        assert user_belongs_to_tenant(session, 100, 200)
        audit_log = session.exec(
            select(SystemLog).where(
                SystemLog.tenant_id == 200,
                SystemLog.operation_detail == "接受企业邀请",
            )
        ).first()
        assert audit_log is not None
        assert audit_log.resource_id == str(invitation.id)

        tenant_rows = asyncio.run(tenant_api.tenant_join_applications(session, tenant_admin, current_tenant))
        assert tenant_rows == []


def test_tenant_admin_can_cancel_pending_invitation():
    engine = _engine()
    tenant_admin = SimpleNamespace(id=2, system_role="viewer", tenant_id=200, tenant_role="admin")
    current_tenant = SimpleNamespace(id=200, code="tenant-b", name="Tenant B", role="admin")
    with Session(engine) as session:
        session.add(TenantModel(id=200, code="tenant-b", name="Tenant B", status=1, plan="basic"))
        invitation = create_tenant_invitation(
            session,
            tenant_id=200,
            invitee_user_id=100,
            invited_by_user_id=2,
            requested_role="member",
        )
        session.commit()

        cancelled = asyncio.run(tenant_api.cancel_tenant_invitation(
            session,
            tenant_admin,
            current_tenant,
            int(invitation.id),
        ))

        assert cancelled.status == "cancelled"
        assert not user_belongs_to_tenant(session, 100, 200)


def test_bulk_invite_records_per_account_results_and_audit():
    engine = _engine()
    tenant_admin = SimpleNamespace(id=2, system_role="viewer", tenant_id=200, tenant_role="admin")
    current_tenant = SimpleNamespace(id=200, code="tenant-b", name="Tenant B", role="admin")
    with Session(engine) as session:
        session.exec(text(
            """
            INSERT INTO sys_user
                (id, account, name, password, email, status, origin, create_time, language, system_role)
            VALUES
                (2, 'tenant-admin', 'Tenant Admin', '', 'admin@example.com', 1, 0, 1, 'zh-CN', 'viewer'),
                (3, 'invitee', 'Invitee', '', 'invitee@example.com', 1, 0, 1, 'zh-CN', 'viewer'),
                (4, 'platform-admin', 'Platform Admin', '', 'platform@example.com', 1, 0, 1, 'zh-CN', 'system_admin')
            """
        ))
        session.add(TenantModel(id=200, code="tenant-b", name="Tenant B", status=1, plan="basic"))
        session.add(TenantUserModel(id=201, tenant_id=200, user_id=2, role="admin", is_primary=True, status=1))
        session.commit()

        results = asyncio.run(tenant_api.bulk_invite_tenant_members(
            session,
            tenant_admin,
            current_tenant,
            TenantBulkInviteCreator(accounts=["invitee", "missing", "platform-admin", "invitee"]),
        ))

        result_by_account = {item.account: item for item in results}
        assert result_by_account["invitee"].status == "created"
        assert result_by_account["invitee"].application_id is not None
        assert result_by_account["missing"].status == "failed"
        assert result_by_account["platform-admin"].status == "failed"
        assert len(results) == 3
        audit_log = session.exec(
            select(SystemLog).where(
                SystemLog.tenant_id == 200,
                SystemLog.operation_detail == "批量邀请企业成员",
            )
        ).first()
        assert audit_log is not None
        assert "created=1" in audit_log.remark


def test_verified_email_domain_auto_assigns_user_after_platform_review_only():
    engine = _engine()
    tenant_admin = SimpleNamespace(id=2, system_role="viewer", tenant_id=200, tenant_role="admin")
    platform_admin = _user(1, "system_admin")
    current_tenant = SimpleNamespace(id=200, code="tenant-b", name="Tenant B", role="admin")
    new_user = SimpleNamespace(id=100, email="new.employee@acme.example")
    with Session(engine) as session:
        session.add(TenantModel(id=200, code="tenant-b", name="Tenant B", status=1, plan="basic"))
        session.add(TenantUserModel(id=201, tenant_id=200, user_id=2, role="admin", is_primary=True, status=1))
        session.commit()

        pending = asyncio.run(tenant_api.bind_tenant_domain(
            session,
            tenant_admin,
            current_tenant,
            TenantDomainCreator(domain="@acme.example", auto_join_role="admin"),
        ))
        assert pending.status == "pending"
        assert auto_assign_tenants_by_email_domain(session, new_user) == []
        assert not user_belongs_to_tenant(session, 100, 200)

        reviewed = asyncio.run(tenant_api.review_domain_binding(
            session,
            platform_admin,
            int(pending.id),
            TenantDomainReview(status="verified", auto_join_role="admin"),
        ))
        assert reviewed.status == "verified"

        assigned = auto_assign_tenants_by_email_domain(session, new_user)

        assert len(assigned) == 1
        assert assigned[0].tenant_id == 200
        assert assigned[0].role == "admin"


def test_tenant_security_policy_blocks_local_login_but_not_platform_admin():
    engine = _engine()
    tenant_admin = SimpleNamespace(id=2, system_role="viewer", tenant_id=200, tenant_role="admin", origin=0)
    current_tenant = SimpleNamespace(id=200, code="tenant-b", name="Tenant B", role="admin")
    with Session(engine) as session:
        session.add(TenantModel(id=200, code="tenant-b", name="Tenant B", status=1, plan="basic"))
        session.commit()

        policy = asyncio.run(tenant_api.update_tenant_security_policy(
            session,
            tenant_admin,
            current_tenant,
            TenantSecurityPolicyEditor(
                sso_required=True,
                session_timeout_minutes=60,
            ),
        ))

        assert policy.sso_required is True
        with pytest.raises(PermissionError, match="SSO"):
            validate_tenant_security_policy(
                session,
                tenant_id=200,
                user=SimpleNamespace(id=100, origin=0, system_role="viewer"),
            )
        validate_tenant_security_policy(
            session,
            tenant_id=200,
            user=SimpleNamespace(id=1, origin=0, system_role="system_admin"),
        )


def test_data_export_request_creates_manifest_after_platform_review():
    engine = _engine()
    tenant_admin = SimpleNamespace(id=2, system_role="viewer", tenant_id=200, tenant_role="admin")
    platform_admin = _user(1, "system_admin")
    current_tenant = SimpleNamespace(id=200, code="tenant-b", name="Tenant B", role="admin")
    with Session(engine) as session:
        session.add(TenantModel(id=200, code="tenant-b", name="Tenant B", status=1, plan="basic"))
        session.exec(text(
            """
            INSERT INTO tenant_export_rows (id, tenant_id, value)
            VALUES (1, 200, 'a'), (2, 200, 'b'), (3, 300, 'other')
            """
        ))
        session.commit()

        submitted = asyncio.run(tenant_api.submit_tenant_data_request(
            session,
            tenant_admin,
            current_tenant,
            TenantDataRequestCreator(request_type="export", reason="customer offboarding"),
        ))
        assert submitted.status == "pending"
        assert submitted.export_manifest is None

        reviewed = asyncio.run(tenant_api.review_data_request(
            session,
            platform_admin,
            int(submitted.id),
            TenantDataRequestReview(approved=True, review_comment="approved"),
        ))

        manifest = json.loads(reviewed.export_manifest)
        export_row_scope = [
            item for item in manifest["tables"] if item["table"] == "tenant_export_rows"
        ]
        assert reviewed.status == "approved"
        assert export_row_scope == [{"table": "tenant_export_rows", "rows": 2}]


def test_tenant_delete_request_is_manual_and_does_not_delete_data_on_completion():
    engine = _engine()
    tenant_owner = SimpleNamespace(id=2, system_role="viewer", tenant_id=200, tenant_role="owner")
    tenant_admin = SimpleNamespace(id=3, system_role="viewer", tenant_id=200, tenant_role="admin")
    platform_admin = _user(1, "system_admin")
    current_tenant = SimpleNamespace(id=200, code="tenant-b", name="Tenant B", role="owner")
    with Session(engine) as session:
        session.add(TenantModel(id=200, code="tenant-b", name="Tenant B", status=1, plan="basic"))
        session.add(TenantUserModel(id=201, tenant_id=200, user_id=2, role="owner", is_primary=True, status=1))
        session.exec(text("INSERT INTO tenant_export_rows (id, tenant_id, value) VALUES (1, 200, 'keep')"))
        session.commit()

        with pytest.raises(HTTPException) as exc:
            asyncio.run(tenant_api.submit_tenant_data_request(
                session,
                tenant_admin,
                current_tenant,
                TenantDataRequestCreator(request_type="delete", reason="not owner"),
            ))
        assert exc.value.status_code == 403

        submitted = asyncio.run(tenant_api.submit_tenant_data_request(
            session,
            tenant_owner,
            current_tenant,
            TenantDataRequestCreator(request_type="delete", reason="tenant cancellation"),
        ))
        reviewed = asyncio.run(tenant_api.review_data_request(
            session,
            platform_admin,
            int(submitted.id),
            TenantDataRequestReview(approved=True, review_comment="manual checklist accepted"),
        ))
        completed = asyncio.run(tenant_api.complete_data_request(
            session,
            platform_admin,
            int(reviewed.id),
            TenantDataRequestComplete(complete_comment="operator finished offline deletion"),
        ))

        assert completed.status == "completed"
        assert session.get(TenantModel, 200) is not None
        assert session.exec(text("SELECT COUNT(*) FROM tenant_export_rows WHERE tenant_id = 200")).one()[0] == 1

        cancellation = asyncio.run(tenant_api.submit_tenant_data_request(
            session,
            tenant_owner,
            current_tenant,
            TenantDataRequestCreator(request_type="cancel", reason="close tenant"),
        ))
        cancellation = asyncio.run(tenant_api.review_data_request(
            session,
            platform_admin,
            int(cancellation.id),
            TenantDataRequestReview(approved=True, review_comment="approved for manual offboarding"),
        ))
        cancellation = asyncio.run(tenant_api.complete_data_request(
            session,
            platform_admin,
            int(cancellation.id),
            TenantDataRequestComplete(complete_comment="operator confirmed manual offboarding"),
        ))
        assert cancellation.status == "completed"
        assert session.get(TenantModel, 200).status == 1


def test_tenant_owner_can_transfer_ownership_to_active_member():
    engine = _engine()
    tenant_owner = SimpleNamespace(id=10, system_role="viewer", tenant_id=200, tenant_role="owner")
    current_tenant = SimpleNamespace(id=200, code="tenant-b", name="Tenant B", role="owner")
    with Session(engine) as session:
        session.exec(text(
            """
            INSERT INTO sys_user
                (id, account, name, password, email, status, origin, create_time, language, system_role)
            VALUES
                (10, 'owner', 'Owner', '', 'owner@example.com', 1, 0, 1, 'zh-CN', 'viewer'),
                (11, 'member', 'Member', '', 'member@example.com', 1, 0, 1, 'zh-CN', 'viewer')
            """
        ))
        session.add(TenantModel(id=200, code="tenant-b", name="Tenant B", status=1, plan="basic"))
        session.add(TenantUserModel(id=201, tenant_id=200, user_id=10, role="owner", is_primary=True, status=1))
        session.add(TenantUserModel(id=202, tenant_id=200, user_id=11, role="member", is_primary=False, status=1))
        session.commit()

        result = asyncio.run(tenant_api.transfer_current_tenant_owner(
            session,
            tenant_owner,
            current_tenant,
            TenantOwnerTransfer(target_user_id=11),
        ))

        previous_owner = session.exec(
            select(TenantUserModel).where(TenantUserModel.tenant_id == 200, TenantUserModel.user_id == 10)
        ).one()
        new_owner = session.exec(
            select(TenantUserModel).where(TenantUserModel.tenant_id == 200, TenantUserModel.user_id == 11)
        ).one()
        assert result.owner_user_id == 11
        assert previous_owner.role == "admin"
        assert new_owner.role == "owner"
        audit_log = session.exec(
            select(SystemLog).where(
                SystemLog.tenant_id == 200,
                SystemLog.operation_detail == "转移企业所有者",
            )
        ).first()
        assert audit_log is not None
        assert audit_log.resource_id == "11"


def test_tenant_admin_cannot_transfer_ownership():
    engine = _engine()
    tenant_admin = SimpleNamespace(id=10, system_role="viewer", tenant_id=200, tenant_role="admin")
    current_tenant = SimpleNamespace(id=200, code="tenant-b", name="Tenant B", role="admin")
    with Session(engine) as session:
        with pytest.raises(HTTPException) as exc:
            asyncio.run(tenant_api.transfer_current_tenant_owner(
                session,
                tenant_admin,
                current_tenant,
                TenantOwnerTransfer(target_user_id=11),
            ))

        assert exc.value.status_code == 403


def test_user_leaves_joined_tenant_and_loses_tenant_project_permissions():
    engine = _engine()
    current_user = SimpleNamespace(id=100, system_role="viewer", tenant_id=1, tenant_role="member", name="Member")
    with Session(engine) as session:
        session.add(TenantModel(id=1, code="default", name="Default", status=1, plan="default"))
        session.add(TenantModel(id=200, code="tenant-b", name="Tenant B", status=1, plan="basic"))
        session.add(TenantUserModel(id=101, tenant_id=1, user_id=100, role="member", is_primary=True, status=1))
        session.add(TenantUserModel(id=201, tenant_id=200, user_id=100, role="member", is_primary=False, status=1))
        session.exec(text("INSERT INTO core_datasource (id, tenant_id, name) VALUES (301, 200, 'Tenant DS')"))
        session.exec(text("INSERT INTO core_datasource_user (id, ds_id, user_id) VALUES (401, 301, 100)"))
        session.commit()

        remaining = asyncio.run(tenant_api.leave_joined_tenant(session, current_user, 200))

        membership = session.exec(
            select(TenantUserModel).where(TenantUserModel.tenant_id == 200, TenantUserModel.user_id == 100)
        ).one()
        datasource_permission = session.exec(text(
            "SELECT id FROM core_datasource_user WHERE ds_id = 301 AND user_id = 100"
        )).first()
        assert membership.status == 0
        assert datasource_permission is None
        assert remaining == []
        audit_log = session.exec(
            select(SystemLog).where(
                SystemLog.tenant_id == 200,
                SystemLog.operation_detail == "退出企业",
            )
        ).first()
        assert audit_log is not None
        assert audit_log.resource_id == "100"


def test_last_tenant_owner_cannot_leave_before_transferring_ownership():
    engine = _engine()
    current_user = SimpleNamespace(id=100, system_role="viewer", tenant_id=200, tenant_role="owner")
    with Session(engine) as session:
        session.add(TenantModel(id=200, code="tenant-b", name="Tenant B", status=1, plan="basic"))
        session.add(TenantUserModel(id=201, tenant_id=200, user_id=100, role="owner", is_primary=True, status=1))
        session.commit()

        with pytest.raises(HTTPException) as exc:
            asyncio.run(tenant_api.leave_joined_tenant(session, current_user, 200))

        assert exc.value.status_code == 400
        membership = session.exec(
            select(TenantUserModel).where(TenantUserModel.tenant_id == 200, TenantUserModel.user_id == 100)
        ).one()
        assert membership.status == 1
