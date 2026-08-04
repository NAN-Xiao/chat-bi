"""Run the three SLG BI Mock data seed stages against one bound datasource."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable

import psycopg2

from core_system_db import core_system_db_config
from slg_bi_datasource import SlgBiDatasourceContext, resolve_slg_bi_datasource_context


REPO_ROOT = Path(__file__).resolve().parents[1]
SYSTEM_DB = core_system_db_config()
EXPEDITION_DASHBOARD_ID = "f2b49b69927740e8bd4c51f38ecf6f7a"
BACKUP_SCRIPT = REPO_ROOT / "tools" / "postgres-backup-local.ps1"


class PipelineStepError(RuntimeError):
    def __init__(self, step: str, return_code: int):
        super().__init__(f"SLG BI generation step failed: {step} (exit {return_code})")
        self.step = step
        self.return_code = return_code


def pipeline_commands(
    context: SlgBiDatasourceContext,
    *,
    python_executable: str = sys.executable,
    recreate: bool = False,
) -> list[tuple[str, list[str]]]:
    connection = context.connection
    backup_command = [
        "powershell",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(BACKUP_SCRIPT),
        "-Action",
        "backup",
        "-HostAddress",
        str(connection["host"]),
        "-Port",
        str(connection["port"]),
        "-Database",
        str(connection["dbname"]),
        "-User",
        str(connection["user"]),
        "-Password",
        str(connection["password"]),
    ]
    base_command = [
        python_executable,
        str(REPO_ROOT / "tools" / "create_slg_bi_mock_db.py"),
        "--host",
        str(connection["host"]),
        "--port",
        str(connection["port"]),
        "--db-name",
        str(connection["dbname"]),
        "--user",
        str(connection["user"]),
        "--password",
        str(connection["password"]),
        "--admin-db",
        "postgres",
    ]
    if recreate:
        base_command.append("--recreate")

    return [
        ("backup", backup_command),
        ("base", base_command),
        (
            "acquisition",
            [python_executable, str(REPO_ROOT / "tools" / "seed_slg_bi_acquisition_dashboard.py")],
        ),
        (
            "expedition",
            [python_executable, str(REPO_ROOT / "tools" / "seed_slg_bi_expedition_dashboard.py")],
        ),
    ]


def run_pipeline(
    context: SlgBiDatasourceContext,
    *,
    runner: Callable[[str, list[str]], int] | None = None,
    python_executable: str = sys.executable,
    recreate: bool = False,
) -> None:
    if runner is None:
        runner = lambda _step, command: subprocess.run(command, check=False).returncode

    for step, command in pipeline_commands(
        context,
        python_executable=python_executable,
        recreate=recreate,
    ):
        print(f"running_step={step}")
        return_code = runner(step, command)
        if return_code != 0:
            raise PipelineStepError(step, return_code)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--recreate",
        action="store_true",
        help="Recreate the bound BI database in the base generation step.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    system_conn = psycopg2.connect(**SYSTEM_DB)
    try:
        context = resolve_slg_bi_datasource_context(system_conn, EXPEDITION_DASHBOARD_ID)
    finally:
        system_conn.close()

    print(
        f"bound_slg_bi_datasource tenant_id={context.tenant_id} "
        f"datasource_id={context.datasource_id} host={context.connection['host']} "
        f"database={context.connection['dbname']}"
    )
    run_pipeline(context, recreate=args.recreate)


if __name__ == "__main__":
    main()
