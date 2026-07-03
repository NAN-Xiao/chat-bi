from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from tools import slg_bi_mock_scheduled_generator as scheduler


ROOT = Path(__file__).resolve().parents[1]


class FakeGenerationStore:
    def __init__(
        self,
        existing: set[str] | None = None,
        existing_behaviors: set[tuple[str, str]] | None = None,
    ) -> None:
        self.existing = set(existing or set())
        self.existing_behaviors = set(existing_behaviors or set())
        self.generated: list[str] = []
        self.generated_behaviors: list[tuple[str, str]] = []
        self.recorded: list[str] = []
        self.recorded_behaviors: list[tuple[str, str]] = []
        self.locked: list[str] = []
        self.released: list[str] = []
        self.behavior_locked: list[tuple[str, str]] = []
        self.behavior_released: list[tuple[str, str]] = []
        self.operations: list[str] = []
        self.cleaned = False
        self.fail_dates: set[str] = set()

    @contextmanager
    def business_date_lock(self, business_date):
        date_key = business_date.isoformat()
        self.locked.append(date_key)
        try:
            yield
        finally:
            self.released.append(date_key)

    @contextmanager
    def behavior_lock(self, cohort_date, business_date):
        key = (cohort_date.isoformat(), business_date.isoformat())
        self.behavior_locked.append(key)
        try:
            yield
        finally:
            self.behavior_released.append(key)

    def is_cohort_generated(self, business_date) -> bool:
        return business_date.isoformat() in self.existing

    def generate_cohort(self, business_date, auto_gen_time: int) -> dict[str, int]:
        date_key = business_date.isoformat()
        self.generated.append(date_key)
        self.operations.append(f"cohort:{date_key}")
        if date_key in self.fail_dates:
            raise RuntimeError("生成失败")
        return {"fact_events": 10, "dim_player": 2}

    def generate_and_record_cohort(self, business_date, business_day_start, auto_gen_time: int) -> dict[str, int]:
        row_counts = self.generate_cohort(business_date, auto_gen_time)
        self.record_cohort_success(business_date, business_day_start, auto_gen_time, row_counts)
        return row_counts

    def record_cohort_success(self, business_date, business_day_start, auto_gen_time: int, row_counts: dict[str, int]) -> None:
        self.recorded.append(business_date.isoformat())
        self.existing.add(business_date.isoformat())

    def is_behavior_generated(self, cohort_date, business_date) -> bool:
        return (cohort_date.isoformat(), business_date.isoformat()) in self.existing_behaviors

    def generate_and_record_existing_user_behavior(
        self,
        cohort_date,
        business_date,
        business_day_start,
        auto_gen_time: int,
    ) -> dict[str, int]:
        key = (cohort_date.isoformat(), business_date.isoformat())
        self.generated_behaviors.append(key)
        self.operations.append(f"behavior:{key[0]}->{key[1]}")
        self.recorded_behaviors.append(key)
        self.existing_behaviors.add(key)
        return {"fact_events": 8, "fact_sessions": 1}

    def cleanup_expired(self, retention_days: int) -> dict[str, int]:
        self.cleaned = True
        self.operations.append("cleanup")
        return {"fact_events": 3}


def test_default_config_targets_slg_bi_mock_test_and_nm_window() -> None:
    config = scheduler.GeneratorConfig()

    assert config.database.name == "slg_bi_mock_test"
    assert config.generator.target_past_days == 7
    assert config.generator.target_future_days == 7
    assert config.generator.new_user_behavior_days == 7


def test_load_config_reads_yaml_and_environment_overrides(tmp_path, monkeypatch) -> None:
    config_file = tmp_path / "slg_mock_generator.yaml"
    config_file.write_text(
        """
database:
  host: 10.0.0.8
  port: 15432
  name: from_yaml
  user: yaml_user
  password: yaml_password
  schema: public

generator:
  timezone: Asia/Shanghai
  target_past_days: 2
  target_future_days: 4
  check_interval_seconds: 120
  retention_days: 30
  new_user_behavior_days: 6
  run_once: false
  daily_players: 99
  seed_base: 100
""",
        encoding="utf-8",
    )
    monkeypatch.setenv("DB_NAME", "from_env")
    monkeypatch.setenv("TARGET_PAST_DAYS", "3")
    monkeypatch.setenv("TARGET_FUTURE_DAYS", "5")
    monkeypatch.setenv("NEW_USER_BEHAVIOR_DAYS", "4")
    monkeypatch.setenv("RUN_ONCE", "true")

    config = scheduler.load_config(str(config_file))

    assert config.database.host == "10.0.0.8"
    assert config.database.name == "from_env"
    assert config.generator.target_past_days == 3
    assert config.generator.target_future_days == 5
    assert config.generator.check_interval_seconds == 120
    assert config.generator.retention_days == 30
    assert config.generator.new_user_behavior_days == 4
    assert config.generator.run_once is True
    assert config.generator.daily_players == 99


def test_resolve_target_business_dates_uses_past_today_and_future_window() -> None:
    now = datetime(2026, 7, 3, 10, 25, tzinfo=ZoneInfo("Asia/Shanghai"))

    dates = scheduler.resolve_target_business_dates(
        now,
        target_past_days=2,
        target_future_days=3,
    )

    assert [day.isoformat() for day in dates] == [
        "2026-07-01",
        "2026-07-02",
        "2026-07-03",
        "2026-07-04",
        "2026-07-05",
        "2026-07-06",
    ]


def test_default_future_window_includes_tomorrow() -> None:
    now = datetime(2026, 7, 3, 10, 25, tzinfo=ZoneInfo("Asia/Shanghai"))

    dates = scheduler.resolve_target_business_dates(
        now,
        target_past_days=scheduler.GeneratorSettings.target_past_days,
        target_future_days=scheduler.GeneratorSettings.target_future_days,
    )

    assert "2026-07-04" in [day.isoformat() for day in dates]


def test_run_once_generates_missing_days_and_records_after_success() -> None:
    now = datetime(2026, 7, 3, 10, 25, tzinfo=ZoneInfo("Asia/Shanghai"))
    store = FakeGenerationStore(existing={"2026-07-02", "2026-07-04"})

    result = scheduler.run_generation_cycle(
        store=store,
        now=now,
        target_past_days=1,
        target_future_days=1,
        new_user_behavior_days=0,
        retention_days=60,
        auto_gen_time=123456,
    )

    assert store.generated == ["2026-07-03"]
    assert store.recorded == ["2026-07-03"]
    assert store.locked == ["2026-07-02", "2026-07-03", "2026-07-04"]
    assert store.released == ["2026-07-02", "2026-07-03", "2026-07-04"]
    assert store.cleaned is True
    assert result["checked_business_dates"] == ["2026-07-02", "2026-07-03", "2026-07-04"]
    assert result["generated_dates"][0]["business_date"] == "2026-07-03"
    assert result["skipped_dates"] == [
        {"business_date": "2026-07-02", "reason": "already_generated"},
        {"business_date": "2026-07-04", "reason": "already_generated"},
    ]


def test_failed_day_is_not_recorded_as_generated() -> None:
    now = datetime(2026, 7, 3, 10, 25, tzinfo=ZoneInfo("Asia/Shanghai"))
    store = FakeGenerationStore()
    store.fail_dates.add("2026-07-03")

    with pytest.raises(RuntimeError, match="生成失败"):
        scheduler.run_generation_cycle(
            store=store,
            now=now,
            target_past_days=0,
            target_future_days=0,
            new_user_behavior_days=0,
            retention_days=60,
            auto_gen_time=123456,
        )

    assert store.generated == ["2026-07-03"]
    assert store.recorded == []
    assert store.locked == ["2026-07-03"]
    assert store.released == ["2026-07-03"]


def test_state_table_schema_records_cohort_and_behavior_success() -> None:
    ddl = scheduler.generation_state_schema_sql()
    create_table_section = ddl[: ddl.index("alter table mock_generation_state")]

    assert "mock_generation_state" in ddl
    assert "generator_id varchar(64) not null" in create_table_section
    assert "state_type text not null" in create_table_section
    assert "cohort_date date not null" in create_table_section
    assert "business_date date not null" in create_table_section
    assert "status text not null default 'success' check (status = 'success')" in create_table_section
    assert "primary key (generator_id, state_type, cohort_date, business_date)" in create_table_section
    assert "running" not in create_table_section
    assert "failed" not in create_table_section
    assert "auto_gen_time bigint" not in create_table_section
    assert "generated_at" not in create_table_section
    assert "row_counts" not in create_table_section
    assert "updated_at" not in create_table_section
    assert "idx_mock_generation_state_auto_gen_time" not in create_table_section


def test_state_table_schema_migrates_old_extra_columns_and_index() -> None:
    ddl = scheduler.generation_state_schema_sql()

    assert "alter table mock_generation_state" in ddl
    assert "alter column generator_id type varchar(64)" in ddl
    assert "add column if not exists state_type" in ddl
    assert "add column if not exists cohort_date" in ddl
    assert "update mock_generation_state" in ddl
    assert "drop column if exists auto_gen_time" in ddl
    assert "drop column if exists generated_at" in ddl
    assert "drop column if exists row_counts" in ddl
    assert "drop column if exists updated_at" in ddl
    assert "drop index if exists idx_mock_generation_state_auto_gen_time" in ddl


def test_postgres_store_uses_business_date_advisory_lock() -> None:
    source = (ROOT / "tools" / "slg_bi_mock_scheduled_generator.py").read_text(encoding="utf-8")

    assert "def business_date_lock(" in source
    assert "pg_advisory_lock(hashtext" in source
    assert "pg_advisory_unlock(hashtext" in source
    assert "slg_bi_mock_scheduled_generator:" in source


def test_postgres_store_passes_cycle_auto_gen_time_to_base_generator() -> None:
    source = (ROOT / "tools" / "slg_bi_mock_scheduled_generator.py").read_text(encoding="utf-8")

    assert "auto_gen_time=auto_gen_time" in source


def test_existing_user_behavior_uses_separate_fact_id_offset() -> None:
    source = (ROOT / "tools" / "slg_bi_mock_scheduled_generator.py").read_text(encoding="utf-8")

    assert "def behavior_fact_id_offset(" in source
    assert "fact_id_offset=behavior_fact_id_offset(cohort_date, business_date)" in source
    assert "force_install_day_zero=True" in source


def test_postgres_store_records_success_inside_base_generator_transaction() -> None:
    source = (ROOT / "tools" / "slg_bi_mock_scheduled_generator.py").read_text(encoding="utf-8")

    assert "def generate_and_record_business_day(" in source
    assert "on_success=record_success" in source
    assert "_record_business_date_success_in_connection" in source


def test_postgres_store_records_success_without_removed_state_columns() -> None:
    source = (ROOT / "tools" / "slg_bi_mock_scheduled_generator.py").read_text(encoding="utf-8")
    insert_section = source[
        source.index("insert into mock_generation_state") : source.index("on conflict (generator_id, state_type, cohort_date, business_date)")
    ]

    assert "auto_gen_time" not in insert_section
    assert "generated_at" not in insert_section
    assert "row_counts" not in insert_section
    assert "updated_at" not in insert_section


def test_run_cycle_cleans_after_cohort_backfill_then_generates_existing_user_behaviors() -> None:
    now = datetime(2026, 7, 3, 10, 25, tzinfo=ZoneInfo("Asia/Shanghai"))
    store = FakeGenerationStore(existing={"2026-07-03"})

    result = scheduler.run_generation_cycle(
        store=store,
        now=now,
        target_past_days=1,
        target_future_days=0,
        new_user_behavior_days=2,
        retention_days=60,
        auto_gen_time=123456,
    )

    assert store.operations == [
        "cohort:2026-07-02",
        "cleanup",
        "behavior:2026-07-01->2026-07-03",
        "behavior:2026-07-02->2026-07-03",
    ]
    assert store.generated_behaviors == [
        ("2026-07-01", "2026-07-03"),
        ("2026-07-02", "2026-07-03"),
    ]
    assert result["generated_behaviors"][0]["cohort_date"] == "2026-07-01"
    assert result["generated_behaviors"][0]["business_date"] == "2026-07-03"


def test_run_cycle_skips_generated_existing_user_behavior_and_never_updates_today_cohort() -> None:
    now = datetime(2026, 7, 3, 10, 25, tzinfo=ZoneInfo("Asia/Shanghai"))
    store = FakeGenerationStore(
        existing={"2026-07-03"},
        existing_behaviors={("2026-07-01", "2026-07-03")},
    )

    result = scheduler.run_generation_cycle(
        store=store,
        now=now,
        target_past_days=0,
        target_future_days=0,
        new_user_behavior_days=2,
        retention_days=60,
        auto_gen_time=123456,
    )

    assert store.generated_behaviors == [("2026-07-02", "2026-07-03")]
    assert ("2026-07-03", "2026-07-03") not in store.generated_behaviors
    assert result["skipped_behaviors"] == [
        {
            "cohort_date": "2026-07-01",
            "business_date": "2026-07-03",
            "reason": "already_generated",
        }
    ]


def test_independent_generator_dockerfile_exists() -> None:
    dockerfile = ROOT / "Dockerfile.slg-mock-generator"
    assert dockerfile.exists()
    content = dockerfile.read_text(encoding="utf-8")

    assert "tools/slg_bi_mock_scheduled_generator.py" in content
    assert "Dockerfile" not in content.replace("Dockerfile.slg-mock-generator", "")
    assert "PyYAML" in content


def test_generator_deploy_config_exists() -> None:
    config_file = ROOT / "deploy" / "slg_mock_generator.yaml"
    assert config_file.exists()
    content = config_file.read_text(encoding="utf-8")

    assert "name: slg_bi_mock_test" in content
    assert "target_past_days: 7" in content
    assert "target_future_days: 7" in content
    assert "new_user_behavior_days: 7" in content
    assert "retention_days: 60" in content
    assert "daily_players: 3000" in content


def test_compose_has_optional_mock_data_profile() -> None:
    compose = (ROOT / "docker-compose.yaml").read_text(encoding="utf-8")

    assert "slg-mock-generator:" in compose
    assert 'profiles: ["mock-data"]' in compose
    assert "Dockerfile.slg-mock-generator" in compose
    assert "./deploy/slg_mock_generator.yaml:/app/config/slg_mock_generator.yaml:ro" in compose
    assert "DB_NAME: slg_bi_mock_test" in compose
