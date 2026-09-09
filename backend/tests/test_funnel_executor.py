from apps.dashboard.crud.funnel_executor import compute_funnel


def test_compute_funnel_sequential_millisecond_events():
    rows = [
        {"entity_id": "u1", "event_name": "a", "event_time": 1_000_000_000_000},
        {"entity_id": "u1", "event_name": "b", "event_time": 1_000_000_001_000},
        {"entity_id": "u1", "event_name": "c", "event_time": 1_000_000_002_000},
        {"entity_id": "u2", "event_name": "a", "event_time": 1_000_000_000_000},
        {"entity_id": "u2", "event_name": "c", "event_time": 1_000_000_001_000},
    ]
    result = compute_funnel(rows, [{"event": "a"}, {"event": "b"}, {"event": "c"}], window={"value": 7, "unit": "day"})
    assert [item["step_count"] for item in result] == [2, 1, 1]
    assert result[1]["step_conversion_rate"] == 0.5


def test_compute_funnel_uses_first_step_window():
    rows = [
        {"entity_id": "u1", "event_name": "a", "event_time": 1_000_000_000_000},
        {"entity_id": "u1", "event_name": "b", "event_time": 1_000_604_801_000},
    ]
    result = compute_funnel(rows, [{"event": "a"}, {"event": "b"}], window={"value": 7, "unit": "day"})
    assert [item["step_count"] for item in result] == [1, 0]


def test_compute_funnel_groups_entities():
    rows = [
        {"entity_id": "u1", "event_name": "a", "event_time": 1, "channel": "x"},
        {"entity_id": "u1", "event_name": "b", "event_time": 2, "channel": "x"},
        {"entity_id": "u2", "event_name": "a", "event_time": 1, "channel": "y"},
    ]
    result = compute_funnel(rows, [{"event": "a"}, {"event": "b"}], group_keys=["channel"])
    assert {(r["channel"], r["step_order"], r["step_count"]) for r in result} == {
        ("x", 1, 1), ("x", 2, 1), ("y", 1, 1), ("y", 2, 0),
    }


def test_compute_funnel_same_day_uses_date_key():
    rows = [
        {"entity_id": "u1", "event_name": "a", "event_time": 1000, "event_date_key": 20260901},
        {"entity_id": "u1", "event_name": "b", "event_time": 2000, "event_date_key": 20260902},
    ]
    result = compute_funnel(rows, [{"event": "a"}, {"event": "b"}], window={"mode": "same_day"})
    assert [item["step_count"] for item in result] == [1, 0]


def test_compute_funnel_related_property_deduplicates_entity_counts():
    rows = [
        {"entity_id": "u1", "event_name": "a", "event_time": 1, "related_value": "r1"},
        {"entity_id": "u1", "event_name": "b", "event_time": 2, "related_value": "r1"},
        {"entity_id": "u1", "event_name": "a", "event_time": 3, "related_value": "r2"},
        {"entity_id": "u1", "event_name": "b", "event_time": 4, "related_value": "r2"},
    ]
    result = compute_funnel(
        rows,
        [{"event": "a"}, {"event": "b"}],
        related_key="related_value",
    )
    assert [item["step_count"] for item in result] == [1, 1]
