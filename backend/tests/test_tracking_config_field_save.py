"""验证数据字典 JSON 字段在写入存储前使用统一身份规则。"""
from __future__ import annotations

import pytest

from apps.system.crud.tracking_config import (
    _tracking_field_json_identity,
    save_tracking_config,
)
from apps.system.schemas.tenant_schema import (
    TenantTrackingConfigEditor,
    TenantTrackingFieldBase,
)


class UnexpectedSession:
    def exec(self, *_args, **_kwargs):
        raise AssertionError("无效 JSON 字段不应访问数据库")


@pytest.mark.parametrize(
    ("field_name", "json_path", "expected_path"),
    [
        ("abtest.1001", "$.1001", '$["1001"]'),
        ("abtest[1001]", "$[1001]", "$[1001]"),
    ],
)
def test_json_field_identity_normalizes_path_without_losing_segment_type(
    field_name: str,
    json_path: str,
    expected_path: str,
) -> None:
    field = TenantTrackingFieldBase(
        table_name="event",
        field_name=field_name,
        source_field="abtest",
        json_path=json_path,
    )

    assert _tracking_field_json_identity(field) == ("abtest", expected_path)


def test_save_rejects_json_field_name_that_disagrees_with_path() -> None:
    editor = TenantTrackingConfigEditor(
        fields=[
            TenantTrackingFieldBase(
                table_name="event",
                field_name='abtest["1001"]',
                source_field="abtest",
                json_path='$["1001"]',
            )
        ]
    )

    with pytest.raises(ValueError, match=r"event.*abtest\.1001"):
        save_tracking_config(UnexpectedSession(), 2001, editor, datasource_id=3)
