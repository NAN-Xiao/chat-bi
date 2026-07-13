"""验证工作空间事件分组的数据模型和引用校验。"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
from fastapi import HTTPException

from apps.system.api import tracking_config as tracking_config_api
from apps.system.crud.tracking_config import (
    _event_group_dto,
    validate_tracking_event_groups,
)
from apps.system.models.tenant import TenantTrackingEventGroupModel
from apps.system.schemas.tenant_schema import (
    TenantTrackingConfigEditor,
    TenantTrackingEventGroupBase,
)


def test_event_group_rejects_unknown_event() -> None:
    groups = [
        TenantTrackingEventGroupBase(
            group_key="payment_process",
            group_name="支付流程事件",
            event_names=["PayFinish2"],
        )
    ]

    with pytest.raises(ValueError, match="PayFinish2"):
        validate_tracking_event_groups(groups, [{"event_name": "PayFinish"}])


def test_event_group_rejects_duplicate_member() -> None:
    groups = [
        TenantTrackingEventGroupBase(
            group_key="payment_process",
            group_name="支付流程事件",
            event_names=["PayFinish", "PayFinish"],
        )
    ]

    with pytest.raises(ValueError, match="重复事件 PayFinish"):
        validate_tracking_event_groups(groups, [{"event_name": "PayFinish"}])


def test_editor_omitted_event_groups_means_preserve() -> None:
    editor = TenantTrackingConfigEditor()

    assert editor.event_groups is None


def test_event_group_model_is_unique_within_tenant_datasource() -> None:
    constraint_columns = {
        tuple(column.name for column in constraint.columns)
        for constraint in TenantTrackingEventGroupModel.__table__.constraints
        if constraint.__class__.__name__ == "UniqueConstraint"
    }

    assert ("tenant_id", "datasource_id", "group_key") in constraint_columns


def test_event_group_dto_preserves_scope_and_member_order() -> None:
    row = TenantTrackingEventGroupModel(
        id=1001,
        tenant_id=2001,
        datasource_id=3,
        group_key="payment_process",
        group_name="支付流程事件",
        description="只统计流程量",
        event_names=["PayBuyRet", "PayFinish"],
        sort_order=10,
        enabled=True,
        create_by=1,
        update_by=2,
        create_time=100,
        update_time=200,
    )

    dto = _event_group_dto(row)

    assert dto.tenant_id == 2001
    assert dto.datasource_id == 3
    assert dto.event_names == ["PayBuyRet", "PayFinish"]
    assert dto.sort_order == 10


def test_event_group_migration_follows_current_alembic_head() -> None:
    migration_path = Path(__file__).parents[1] / "alembic" / "versions" / "142_tracking_event_groups.py"
    spec = importlib.util.spec_from_file_location("tracking_event_group_migration", migration_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)

    spec.loader.exec_module(module)

    assert module.revision == "142trackinggroups"
    assert module.down_revision == "141trackingextra"


def test_tracking_config_save_validation_rolls_back_and_returns_400(monkeypatch) -> None:
    class FakeSession:
        rolled_back = False

        def rollback(self) -> None:
            self.rolled_back = True

    def fail_save(*_args, **_kwargs):
        raise ValueError("事件分组 payment_process 引用了未知事件 PayFinish2")

    session = FakeSession()
    monkeypatch.setattr(tracking_config_api, "save_tracking_config", fail_save)

    with pytest.raises(HTTPException) as error:
        tracking_config_api._save_tracking_config_or_400(
            session,
            tenant_id=2001,
            editor=TenantTrackingConfigEditor(),
            datasource_id=3,
            current_user_id=1,
        )

    assert error.value.status_code == 400
    assert "PayFinish2" in str(error.value.detail)
    assert session.rolled_back is True
