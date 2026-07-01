from apps.external_mcp.crud import _normalize_external_mcp_preview_rows


def test_external_mcp_numeric_mapping_preview_rows_are_ranked_descending():
    fields, rows = _normalize_external_mcp_preview_rows(
        {
            "bug_or_abnormal": 14,
            "activity_reward_or_matchmaking_dissatisfaction": 6,
            "community_safety_risk": 8,
            "payment_monetization": 1,
        }
    )

    assert fields == ["name", "value"]
    assert rows == [
        {"name": "bug_or_abnormal", "value": 14},
        {"name": "community_safety_risk", "value": 8},
        {"name": "activity_reward_or_matchmaking_dissatisfaction", "value": 6},
        {"name": "payment_monetization", "value": 1},
    ]


def test_external_mcp_nested_numeric_mapping_preview_rows_are_ranked_descending():
    _fields, rows = _normalize_external_mcp_preview_rows(
        {
            "timezone": "Asia/Shanghai",
            "total": 38,
            "by_risk_category": {
                "activity_reward_or_matchmaking_dissatisfaction": 6,
                "bug_or_abnormal": 14,
                "community_safety_risk": 8,
            },
        }
    )

    nested_rows = [row for row in rows if row.get("group") == "by_risk_category"]
    assert nested_rows == [
        {"name": "bug_or_abnormal", "value": 14, "group": "by_risk_category"},
        {"name": "community_safety_risk", "value": 8, "group": "by_risk_category"},
        {"name": "activity_reward_or_matchmaking_dissatisfaction", "value": 6, "group": "by_risk_category"},
    ]


def test_external_mcp_list_preview_rows_keep_source_order():
    _fields, rows = _normalize_external_mcp_preview_rows(
        [
            {"name": "second", "value": 2},
            {"name": "first", "value": 10},
        ]
    )

    assert rows == [
        {"name": "second", "value": 2},
        {"name": "first", "value": 10},
    ]
