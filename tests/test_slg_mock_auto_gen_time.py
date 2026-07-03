from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
GENERATOR = ROOT / "tools" / "create_slg_bi_mock_db_prod.py"

GENERATED_TABLES = [
    "dim_server",
    "dim_alliance",
    "dim_product",
    "dim_event_name",
    "dim_player",
    "fact_sessions",
    "fact_events",
    "fact_payments",
    "fact_battles",
    "fact_resource_transactions",
    "fact_building_upgrades",
    "fact_research",
    "fact_army_training",
]


def _source() -> str:
    return GENERATOR.read_text(encoding="utf-8")


def _create_table_body(source: str, table_name: str) -> str:
    match = re.search(
        rf"create table (?:if not exists )?{re.escape(table_name)} \(\n(?P<body>.*?)\n    \);",
        source,
        re.S,
    )
    assert match, f"未找到 {table_name} 的建表 DDL"
    return match.group("body")


def test_all_generated_tables_define_auto_gen_time_column() -> None:
    source = _source()

    for table_name in GENERATED_TABLES:
        body = _create_table_body(source, table_name)
        assert "auto_gen_time bigint not null default 0" in body, f"{table_name} 缺少 auto_gen_time 字段"


def test_auto_gen_time_has_comment_and_indexes() -> None:
    source = _source()
    comment = "数据自动生成时间 用于自动清理数据 和业务逻辑无关 不用于数据分析"

    assert f'"auto_gen_time": "{comment}"' in source
    for table_name in GENERATED_TABLES:
        assert f"comment on column {table_name}.auto_gen_time is '{comment}'" in source
        assert f"idx_{table_name}_auto_gen_time" in source


def test_copy_rows_explicitly_writes_auto_gen_time() -> None:
    source = _source()

    for table_name in GENERATED_TABLES:
        pattern = rf'copy_rows\(conn, "{re.escape(table_name)}", \[(?P<columns>.*?)\],'
        match = re.search(pattern, source, re.S)
        assert match, f"未找到 {table_name} 的 copy_rows 调用"
        assert '"auto_gen_time"' in match.group("columns"), f"{table_name} 插入列未显式写入 auto_gen_time"


def test_generated_rows_share_current_auto_gen_time_variable() -> None:
    source = _source()

    assert "import time" in source
    assert "auto_gen_time = int(getattr(args, \"auto_gen_time\", 0)) or int(time.time())" in source


def test_cleanup_uses_auto_gen_time_without_touching_manual_rows() -> None:
    source = _source()

    assert "def cleanup_expired_auto_generated_rows(" in source
    assert "auto_gen_time > 0" in source
    assert "extract(epoch from now() - (%s * interval '1 day'))::bigint" in source
    assert "fact_payments" in source
    assert "fact_events" in source
    assert "dim_player" in source


def test_schema_and_indexes_are_idempotent_for_scheduled_generation() -> None:
    source = _source()

    for table_name in GENERATED_TABLES:
        assert f"create table if not exists {table_name}" in source
        assert f"create index if not exists idx_{table_name}_auto_gen_time" in source
        assert f"alter table {table_name} add column if not exists auto_gen_time bigint not null default 0" in source


def test_copy_rows_does_not_commit_each_table_so_daily_generation_is_atomic() -> None:
    source = _source()
    match = re.search(
        r"def copy_rows\(.*?\n\n\ndef cleanup_expired_auto_generated_rows",
        source,
        re.S,
    )
    assert match, "未找到 copy_rows 函数体"

    assert "conn.commit()" not in match.group(0)


def test_auto_gen_time_columns_are_added_before_comments_for_existing_tables() -> None:
    source = _source()

    assert source.index("cur.execute(auto_gen_time_ddl)") < source.index("cur.execute(auto_gen_time_comment_ddl)")


def test_generate_invokes_success_callback_before_final_commit() -> None:
    source = _source()

    assert 'on_success = getattr(args, "on_success", None)' in source
    assert "on_success(conn, counts)" in source
    assert source.index("on_success(conn, counts)") < source.index("conn.commit()", source.index("on_success(conn, counts)"))
