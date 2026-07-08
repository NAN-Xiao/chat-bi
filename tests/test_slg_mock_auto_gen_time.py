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
        if table_name == "dim_player":
            player_columns_section = source[
                source.index("player_columns = [") : source.index(
                    "copy_rows(conn, \"dim_server\"",
                    source.index("player_columns = ["),
                )
            ]
            assert '"auto_gen_time"' in player_columns_section
            continue
        pattern = rf'copy_rows\(conn, "{re.escape(table_name)}", \[(?P<columns>.*?)\],'
        match = re.search(pattern, source, re.S)
        assert match, f"未找到 {table_name} 的 copy_rows 调用"
        assert '"auto_gen_time"' in match.group("columns"), f"{table_name} 插入列未显式写入 auto_gen_time"


def test_generated_rows_share_current_auto_gen_time_variable() -> None:
    source = _source()

    assert "import time" in source
    assert "auto_gen_time = int(getattr(args, \"auto_gen_time\", 0)) or int(time.time())" in source


def test_base_generator_default_daily_players_is_3000() -> None:
    source = _source()

    assert 'parser.add_argument("--players", type=int, default=3000)' in source


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


def test_generate_can_replay_cohort_but_write_only_one_behavior_date() -> None:
    source = _source()

    assert 'write_date_value = getattr(args, "write_date", None)' in source
    assert 'fact_id_offset = int(getattr(args, "fact_id_offset", id_offset))' in source
    assert "big_id_offset = fact_id_offset * 1000" in source
    assert 'force_install_day_zero = bool(getattr(args, "force_install_day_zero", False))' in source
    assert "install_indices = [0] * args.players" in source
    assert "filter_rows_for_write_date" in source
    assert "session_rows = filter_rows_for_write_date(session_rows, 7, write_date)" in source
    assert "event_rows = filter_rows_for_write_date(event_rows, 7, write_date)" in source
    assert "payment_rows = filter_rows_for_write_date(payment_rows, 4, write_date)" in source
    assert "battle_rows = filter_rows_for_write_date(battle_rows, 6, write_date)" in source
    assert "resource_rows = filter_rows_for_write_date(resource_rows, 4, write_date)" in source
    assert "upsert_player_dimension" in source


def test_replayed_task_detail_rows_keep_only_available_event_references() -> None:
    source = _source()

    assert "filter_rows_for_available_events" in source
    assert "available_event_uids = {row[0] for row in event_rows}" in source
    assert "building_rows = filter_rows_for_available_events(building_rows, 2, 3, available_event_uids)" in source
    assert "research_rows = filter_rows_for_available_events(research_rows, 2, 3, available_event_uids)" in source
    assert "training_rows = filter_rows_for_available_events(training_rows, 2, 3, available_event_uids)" in source
