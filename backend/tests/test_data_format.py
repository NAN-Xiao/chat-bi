from common.utils.data_format import DataFormat


def test_dotted_metric_alias_is_not_expanded_as_qualified_column():
    row = {"dt": "2026-07-21", "指标 1.总次数": 1021}

    normalized = DataFormat.normalize_qualified_sql_column_keys(row)

    assert normalized == row


def test_qualified_column_still_exposes_unqualified_key():
    row = {"event.uid": "user-1"}

    normalized = DataFormat.normalize_qualified_sql_column_keys(row)

    assert normalized == {"event.uid": "user-1", "uid": "user-1"}
