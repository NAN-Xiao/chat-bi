import json

from common.utils.utils import extract_nested_json


def test_extract_nested_json_ignores_brackets_inside_sql_string() -> None:
    payload = {
        "success": True,
        "sql": (
            "SELECT COUNT(*) AS `[500, 1000)` FROM `user` "
            "WHERE `dt` BETWEEN {{dashboard_start_yyyymmdd}} "
            "AND {{dashboard_end_yyyymmdd}}"
        ),
        "tables": ["user"],
        "chart-type": "table",
        "date_filter": {
            "time_field": "dt",
            "date_parameter_type": "yyyymmdd_number",
            "date_expression": {
                "version": 1,
                "mode": "preset",
                "preset": "past_30_days",
            },
        },
    }
    response = f"```json\n{json.dumps(payload, ensure_ascii=False)}\n```"

    extracted = extract_nested_json(response)

    assert extracted is not None
    assert json.loads(extracted)["date_filter"] == payload["date_filter"]
