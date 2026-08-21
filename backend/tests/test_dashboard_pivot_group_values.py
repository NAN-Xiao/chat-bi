from apps.dashboard.models.dashboard_model import DashboardPivotRequest


def test_explicit_all_mode_clears_enumerated_group_values() -> None:
    pivot = DashboardPivotRequest.model_validate(
        {"group_value_mode": "all", "group_values": ["Organic", "Facebook"]}
    )

    assert pivot.group_value_mode == "all"
    assert pivot.group_values == []


def test_custom_mode_preserves_selected_group_values() -> None:
    pivot = DashboardPivotRequest.model_validate(
        {"group_value_mode": "custom", "group_values": ["Organic"]}
    )

    assert pivot.group_value_mode == "custom"
    assert pivot.group_values == ["Organic"]


def test_legacy_nonempty_group_values_remain_custom() -> None:
    pivot = DashboardPivotRequest.model_validate({"group_values": ["Organic"]})

    assert pivot.group_value_mode == "custom"
    assert pivot.group_values == ["Organic"]


def test_legacy_empty_group_values_become_dynamic_all() -> None:
    pivot = DashboardPivotRequest.model_validate({"group_values": []})

    assert pivot.group_value_mode == "all"
    assert pivot.group_values == []
