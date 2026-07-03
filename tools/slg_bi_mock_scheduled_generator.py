from __future__ import annotations

import argparse
import json
import os
import time
from contextlib import contextmanager
from dataclasses import dataclass, field, replace
from datetime import date, datetime, time as datetime_time, timedelta
from pathlib import Path
from typing import Protocol
from zoneinfo import ZoneInfo

import psycopg

try:
    from . import create_slg_bi_mock_db_prod as base_generator
except ImportError:  # pragma: no cover - script execution path
    import create_slg_bi_mock_db_prod as base_generator


GENERATOR_ID = "slg_bi_mock_scheduled_generator"
LOCK_KEY_PREFIX = "slg_bi_mock_scheduled_generator:"
DEFAULT_CONFIG_FILE = "/app/config/slg_mock_generator.yaml"
ID_OFFSET_BASE_DATE = date(2020, 1, 1)


@dataclass(frozen=True)
class DatabaseConfig:
    host: str = "127.0.0.1"
    port: int = 5432
    name: str = "slg_bi_mock_test"
    user: str = "postgres"
    password: str = "111111"
    schema: str = "public"


@dataclass(frozen=True)
class GeneratorSettings:
    timezone: str = "Asia/Shanghai"
    target_past_days: int = 7
    target_future_days: int = 7
    check_interval_seconds: int = 3600
    retention_days: int = 60
    run_once: bool = False
    log_level: str = "INFO"
    daily_players: int = 8000
    seed_base: int = 20260613


@dataclass(frozen=True)
class GeneratorConfig:
    database: DatabaseConfig = field(default_factory=DatabaseConfig)
    generator: GeneratorSettings = field(default_factory=GeneratorSettings)


class GenerationStore(Protocol):
    def business_date_lock(self, business_date: date):
        ...

    def is_business_date_generated(self, business_date: date) -> bool:
        ...

    def generate_and_record_business_day(
        self,
        business_date: date,
        business_day_start: datetime,
        auto_gen_time: int,
    ) -> dict[str, int]:
        ...

    def cleanup_expired(self, retention_days: int) -> dict[str, int]:
        ...


def _read_yaml_config(config_file: str | None) -> dict:
    if not config_file:
        return {}
    path = Path(config_file)
    if not path.exists():
        return {}
    content = path.read_text(encoding="utf-8")
    try:
        import yaml
    except ImportError:
        return _parse_simple_yaml_config(content)
    data = yaml.safe_load(content)
    return data or {}


def _parse_simple_yaml_config(content: str) -> dict:
    data: dict[str, dict[str, object]] = {}
    current_section: str | None = None
    for raw_line in content.splitlines():
        line = raw_line.split("#", 1)[0].rstrip()
        if not line.strip():
            continue
        if not line.startswith(" ") and line.endswith(":"):
            current_section = line[:-1].strip()
            data[current_section] = {}
            continue
        if current_section is None or ":" not in line:
            continue
        key, value = line.strip().split(":", 1)
        data[current_section][key.strip()] = _parse_scalar(value.strip())
    return data


def _parse_scalar(value: str) -> object:
    if value.startswith(('"', "'")) and value.endswith(('"', "'")):
        return value[1:-1]
    lowered = value.lower()
    if lowered == "true":
        return True
    if lowered == "false":
        return False
    try:
        return int(value)
    except ValueError:
        return value


def _env_int(name: str, current: int) -> int:
    value = os.getenv(name)
    return current if value is None or value == "" else int(value)


def _env_bool(name: str, current: bool) -> bool:
    value = os.getenv(name)
    if value is None or value == "":
        return current
    return value.lower() in {"1", "true", "yes", "y", "on"}


def load_config(config_file: str | None = None) -> GeneratorConfig:
    data = _read_yaml_config(config_file or os.getenv("CONFIG_FILE"))
    database_data = data.get("database", {})
    generator_data = data.get("generator", {})

    database = DatabaseConfig(
        host=str(database_data.get("host", DatabaseConfig.host)),
        port=int(database_data.get("port", DatabaseConfig.port)),
        name=str(database_data.get("name", DatabaseConfig.name)),
        user=str(database_data.get("user", DatabaseConfig.user)),
        password=str(database_data.get("password", DatabaseConfig.password)),
        schema=str(database_data.get("schema", DatabaseConfig.schema)),
    )
    generator = GeneratorSettings(
        timezone=str(generator_data.get("timezone", GeneratorSettings.timezone)),
        target_past_days=int(generator_data.get("target_past_days", GeneratorSettings.target_past_days)),
        target_future_days=int(generator_data.get("target_future_days", GeneratorSettings.target_future_days)),
        check_interval_seconds=int(generator_data.get("check_interval_seconds", GeneratorSettings.check_interval_seconds)),
        retention_days=int(generator_data.get("retention_days", GeneratorSettings.retention_days)),
        run_once=bool(generator_data.get("run_once", GeneratorSettings.run_once)),
        log_level=str(generator_data.get("log_level", GeneratorSettings.log_level)),
        daily_players=int(generator_data.get("daily_players", GeneratorSettings.daily_players)),
        seed_base=int(generator_data.get("seed_base", GeneratorSettings.seed_base)),
    )

    database = replace(
        database,
        host=os.getenv("DB_HOST", database.host),
        port=_env_int("DB_PORT", database.port),
        name=os.getenv("DB_NAME", database.name),
        user=os.getenv("DB_USER", database.user),
        password=os.getenv("DB_PASSWORD", database.password),
        schema=os.getenv("DB_SCHEMA", database.schema),
    )
    generator = replace(
        generator,
        timezone=os.getenv("TIMEZONE", generator.timezone),
        target_past_days=_env_int("TARGET_PAST_DAYS", generator.target_past_days),
        target_future_days=_env_int("TARGET_FUTURE_DAYS", generator.target_future_days),
        check_interval_seconds=_env_int("CHECK_INTERVAL_SECONDS", generator.check_interval_seconds),
        retention_days=_env_int("RETENTION_DAYS", generator.retention_days),
        run_once=_env_bool("RUN_ONCE", generator.run_once),
        log_level=os.getenv("LOG_LEVEL", generator.log_level),
        daily_players=_env_int("DAILY_PLAYERS", generator.daily_players),
        seed_base=_env_int("SEED_BASE", generator.seed_base),
    )
    return GeneratorConfig(database=database, generator=generator)


def resolve_target_business_dates(now: datetime, target_past_days: int, target_future_days: int) -> list[date]:
    if target_past_days < 0 or target_future_days < 0:
        raise ValueError("target_past_days 和 target_future_days 不能为负数")
    today = now.date()
    return [today + timedelta(days=offset) for offset in range(-target_past_days, target_future_days + 1)]


def business_day_start(business_date: date, timezone: str) -> datetime:
    return datetime.combine(business_date, datetime_time(0, 0, 0), tzinfo=ZoneInfo(timezone))


def generation_state_schema_sql() -> str:
    return """
create table if not exists mock_generation_state (
    generator_id varchar(64) not null,
    business_date date not null,
    business_day_start timestamptz not null,
    status text not null default 'success' check (status = 'success'),
    primary key (generator_id, business_date)
);
alter table mock_generation_state
    alter column generator_id type varchar(64) using generator_id::varchar(64),
    drop column if exists auto_gen_time,
    drop column if exists generated_at,
    drop column if exists row_counts,
    drop column if exists updated_at;
drop index if exists idx_mock_generation_state_auto_gen_time;
""".strip()


class PostgresGenerationStore:
    def __init__(self, config: GeneratorConfig) -> None:
        self.config = config

    def _connect(self) -> psycopg.Connection:
        db = self.config.database
        return psycopg.connect(host=db.host, port=db.port, dbname=db.name, user=db.user, password=db.password)

    def ensure_schema(self) -> None:
        with self._connect() as conn:
            base_generator.create_schema(conn)
            with conn.cursor() as cur:
                cur.execute(generation_state_schema_sql())
            conn.commit()

    @contextmanager
    def business_date_lock(self, business_date: date):
        lock_key = f"{LOCK_KEY_PREFIX}{business_date.isoformat()}"
        conn = self._connect()
        try:
            with conn.cursor() as cur:
                cur.execute("select pg_advisory_lock(hashtext(%s))", (lock_key,))
            yield
        finally:
            try:
                with conn.cursor() as cur:
                    cur.execute("select pg_advisory_unlock(hashtext(%s))", (lock_key,))
                conn.commit()
            finally:
                conn.close()

    def is_business_date_generated(self, business_date: date) -> bool:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                """
                select 1
                from mock_generation_state
                where generator_id = %s
                  and business_date = %s
                  and status = 'success'
                """,
                (GENERATOR_ID, business_date),
            )
            return cur.fetchone() is not None

    def generate_and_record_business_day(
        self,
        business_date: date,
        business_day_start: datetime,
        auto_gen_time: int,
    ) -> dict[str, int]:
        def record_success(conn: psycopg.Connection, _row_counts: dict[str, int]) -> None:
            self._record_business_date_success_in_connection(
                conn,
                business_date,
                business_day_start,
            )

        args = argparse.Namespace(
            host=self.config.database.host,
            port=self.config.database.port,
            db_name=self.config.database.name,
            user=self.config.database.user,
            password=self.config.database.password,
            players=self.config.generator.daily_players,
            start_date=business_date.isoformat(),
            days=1,
            seed=self.config.generator.seed_base + int(business_date.strftime("%Y%m%d")),
            id_offset=business_day_id_offset(business_date),
            auto_gen_time=auto_gen_time,
            on_success=record_success,
        )
        return base_generator.generate(args)

    def _record_business_date_success_in_connection(
        self,
        conn: psycopg.Connection,
        business_date: date,
        business_day_start: datetime,
    ) -> None:
        with conn.cursor() as cur:
            cur.execute(
                """
                insert into mock_generation_state (
                    generator_id,
                    business_date,
                    business_day_start,
                    status
                )
                values (%s, %s, %s, 'success')
                on conflict (generator_id, business_date) do update
                set status = 'success',
                    business_day_start = excluded.business_day_start
                """,
                (GENERATOR_ID, business_date, business_day_start),
            )

    def cleanup_expired(self, retention_days: int) -> dict[str, int]:
        with self._connect() as conn:
            counts = base_generator.cleanup_expired_auto_generated_rows(conn, retention_days=retention_days)
            conn.commit()
            return counts


def business_day_id_offset(business_date: date) -> int:
    return (business_date - ID_OFFSET_BASE_DATE).days * 100000


def run_generation_cycle(
    *,
    store: GenerationStore,
    now: datetime,
    target_past_days: int,
    target_future_days: int,
    retention_days: int,
    auto_gen_time: int | None = None,
    timezone: str = "Asia/Shanghai",
) -> dict:
    auto_gen_time = int(time.time()) if auto_gen_time is None else auto_gen_time
    target_dates = resolve_target_business_dates(now, target_past_days, target_future_days)
    result = {
        "checked_business_dates": [business_date.isoformat() for business_date in target_dates],
        "generated_dates": [],
        "skipped_dates": [],
        "cleanup": {},
    }

    for business_date in target_dates:
        with store.business_date_lock(business_date):
            if store.is_business_date_generated(business_date):
                result["skipped_dates"].append({"business_date": business_date.isoformat(), "reason": "already_generated"})
                continue
            day_start = business_day_start(business_date, timezone)
            row_counts = store.generate_and_record_business_day(business_date, day_start, auto_gen_time)
            result["generated_dates"].append(
                {
                    "business_date": business_date.isoformat(),
                    "business_day_start": day_start.isoformat(),
                    "auto_gen_time": auto_gen_time,
                    "row_counts": row_counts,
                }
            )

    result["cleanup"] = store.cleanup_expired(retention_days)
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run scheduled SLG BI mock data generation.")
    parser.add_argument("--config-file", default=os.getenv("CONFIG_FILE", DEFAULT_CONFIG_FILE))
    parser.add_argument("--run-once", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config = load_config(args.config_file)
    if args.run_once:
        config = replace(config, generator=replace(config.generator, run_once=True))
    store = PostgresGenerationStore(config)
    store.ensure_schema()

    while True:
        now = datetime.now(ZoneInfo(config.generator.timezone))
        result = run_generation_cycle(
            store=store,
            now=now,
            target_past_days=config.generator.target_past_days,
            target_future_days=config.generator.target_future_days,
            retention_days=config.generator.retention_days,
            timezone=config.generator.timezone,
        )
        print(json.dumps(result, ensure_ascii=False), flush=True)
        if config.generator.run_once:
            return
        time.sleep(config.generator.check_interval_seconds)


if __name__ == "__main__":
    main()
