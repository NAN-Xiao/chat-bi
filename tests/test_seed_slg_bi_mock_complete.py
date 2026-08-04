from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
TOOLS_DIR = REPO_ROOT / "tools"
MODULE_PATH = TOOLS_DIR / "seed_slg_bi_mock_complete.py"


def load_module():
    if not MODULE_PATH.exists():
        return None
    sys.path.insert(0, str(TOOLS_DIR))
    spec = importlib.util.spec_from_file_location("seed_slg_bi_mock_complete", MODULE_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_pipeline_runs_backup_base_acquisition_expedition_in_order() -> None:
    module = load_module()
    assert module is not None, "complete SLG BI pipeline script is missing"
    context = module.SlgBiDatasourceContext(
        tenant_id=10,
        datasource_id=20,
        connection={
            "host": "db.example",
            "port": 5432,
            "dbname": "slg_bi_mock",
            "user": "postgres",
            "password": "secret",
        },
    )
    calls = []

    def runner(label, _command):
        calls.append(label)
        return 0

    module.run_pipeline(context, runner=runner, python_executable="python", recreate=True)

    assert calls == ["backup", "base", "acquisition", "expedition"]


def test_pipeline_stops_after_failed_step() -> None:
    module = load_module()
    assert module is not None, "complete SLG BI pipeline script is missing"
    context = module.SlgBiDatasourceContext(
        tenant_id=10,
        datasource_id=20,
        connection={"host": "db.example", "port": 5432, "dbname": "slg_bi_mock", "user": "u", "password": "p"},
    )
    calls = []

    def runner(label, _command):
        calls.append(label)
        return 1 if label == "acquisition" else 0

    try:
        module.run_pipeline(context, runner=runner, python_executable="python", recreate=True)
    except module.PipelineStepError as exc:
        assert exc.step == "acquisition"
    else:
        raise AssertionError("Expected pipeline failure to stop execution")

    assert calls == ["backup", "base", "acquisition"]


def test_commands_pass_bound_database_instead_of_local_defaults() -> None:
    module = load_module()
    assert module is not None, "complete SLG BI pipeline script is missing"
    context = module.SlgBiDatasourceContext(
        tenant_id=10,
        datasource_id=20,
        connection={
            "host": "bound-db.example",
            "port": 5544,
            "dbname": "bound_slg",
            "user": "bound_user",
            "password": "bound_password",
        },
    )

    commands = module.pipeline_commands(context, python_executable="python", recreate=False)
    base_command = commands[1][1]

    assert base_command[base_command.index("--host") + 1] == "bound-db.example"
    assert base_command[base_command.index("--port") + 1] == "5544"
    assert base_command[base_command.index("--db-name") + 1] == "bound_slg"
    assert base_command[base_command.index("--user") + 1] == "bound_user"
    assert "127.0.0.1" not in base_command
    assert "--recreate" not in base_command


def test_acquisition_stage_resolves_the_bound_datasource() -> None:
    source = (TOOLS_DIR / "seed_slg_bi_acquisition_dashboard.py").read_text(encoding="utf-8")

    assert "resolve_slg_bi_datasource_context" in source
    assert "BI_DB = {" not in source
    assert "DATASOURCE_ID = 1" not in source
