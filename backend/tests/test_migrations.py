from pathlib import Path
from unittest.mock import Mock


def test_run_migrations_uses_locale_independent_in_memory_alembic_config(monkeypatch) -> None:
    import common.core.migrations as migrations

    config = Mock()
    command = Mock()
    monkeypatch.setattr(migrations, "Config", config)
    monkeypatch.setattr(migrations, "command", command)

    migrations.run_migrations()

    config.assert_called_once_with()
    script_location = Path(config.return_value.set_main_option.call_args.args[1])
    assert config.return_value.set_main_option.call_args.args[0] == "script_location"
    assert script_location.name == "alembic"
    command.upgrade.assert_called_once_with(config.return_value, "head")
