"""Regression tests for datasource-scoped First Zombie dashboard migration."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
TOOLS_DIR = ROOT / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))


def test_repair_matches_only_known_stale_semantic_view() -> None:
    from copy import deepcopy

    from repair_flam_first_zombie_semantic_dashboards import (
        TargetView,
        repair_view,
        sql_fingerprint,
    )

    stale_view = {
        "chart": {"title": "各建筑升级次数", "series": [{"name": "旧字段", "value": "旧字段"}]},
        "pivot": {"enabled": True, "group_field": "旧字段"},
        "sql": "SELECT JSON_UNQUOTE(JSON_EXTRACT(e.ext, '$.ed_buildingId')) FROM `event` e",
    }
    target = TargetView(
        dashboard_id="dashboard-id",
        view_id="view-id",
        title="各建筑升级次数",
        legacy_sql_sha256=sql_fingerprint(stale_view["sql"]),
        source_key="remaining:82f560ee39f2409485e7270d2c9db26c",
    )

    assert repair_view(stale_view, target) is True
    assert "JSON_EXTRACT(e.personal, '$.ed_buildingId')" in stale_view["sql"]
    assert "series" not in stale_view["chart"]
    assert "pivot" not in stale_view

    unrelated_view = {"chart": {"title": "各建筑升级次数"}, "sql": "SELECT 1"}
    unrelated_before = deepcopy(unrelated_view)
    assert repair_view(unrelated_view, target) is False
    assert unrelated_view == unrelated_before


def test_strict_migration_includes_newly_audited_activity_and_gift_views() -> None:
    from repair_flam_first_zombie_semantic_dashboards import TARGET_VIEWS

    targets = {
        (target.dashboard_id, target.view_id, target.title, target.legacy_sql_sha256, target.source_key)
        for target in TARGET_VIEWS
    }

    assert {
        (
            "29ea652e2969440b91899cfb254dd0ca",
            "9684a569ed034fb0b8a106a9817effaa",
            "参与新手活动的后续7日留存率",
            "ada62e0a5c2689f564dc19d5466b6aec6496b88eb67e9df97a03f59eb7414964",
            "remaining:9684a569ed034fb0b8a106a9817effaa",
        ),
        (
            "29ea652e2969440b91899cfb254dd0ca",
            "095b1cf41cd64844b1f78f07ceccb7bf",
            "参与节日活动的后续7日付费留存率",
            "79baccc6a160d5810325309a5799a1d6b99c56974bba0aef268fe998356a4706",
            "remaining:095b1cf41cd64844b1f78f07ceccb7bf",
        ),
        (
            "0431e8aa54d5444f9de8aef574e21881",
            "15da41b65ee64aba854e2de701a728bc",
            "购买新手礼包用户复购率",
            "5258b32bfbe0f288a693175c7dfa5ca5c1b63482633b970ea7ad65f39282bf0e",
            "remaining:15da41b65ee64aba854e2de701a728bc",
        ),
        (
            "0431e8aa54d5444f9de8aef574e21881",
            "f113ac14e8994d12814452040b702424",
            "购买月卡用户的30日留存",
            "3bd247bd47314024274a339d9fabde1adde5bfc7a44f29723cc5d962011744e6",
            "remaining:f113ac14e8994d12814452040b702424",
        ),
        (
            "4bae835c4243481b9963122b5275ed81",
            "440303dfdf39408ba86ffb222f3334f2",
            "竞技场/出征平均战力",
            "a09d1afa778f1ea1f239b7bcb4de3a7583cc73a79381f17f018439512253ff2b",
            "remaining:440303dfdf39408ba86ffb222f3334f2",
        ),
    } <= targets


def test_remaining_dashboard_repair_does_not_require_optional_realtime_view() -> None:
    from flam_first_zombie_remaining_dashboard_sql import REMAINING_VIEW_SQL
    from repair_flam_first_zombie_remaining_dashboards import missing_required_views

    assert missing_required_views(set(REMAINING_VIEW_SQL)) == []


@pytest.mark.parametrize(
    ("legacy_sql", "apply", "expects_lock"),
    [
        ("SELECT legacy_a", False, False),
        ("SELECT legacy_b", False, False),
        ("SELECT legacy_a", True, True),
        ("SELECT legacy_b", True, True),
    ],
)
def test_semantic_dashboard_migration_locks_only_apply_runs_and_reports_single_outcome(
    monkeypatch,
    legacy_sql,
    apply,
    expects_lock,
) -> None:
    from repair_flam_first_zombie_semantic_dashboards import (
        DATASOURCE_ID,
        TENANT_ID,
        TargetView,
        repair_dashboards,
        sql_fingerprint,
    )

    target_a = TargetView(
        dashboard_id="dashboard-id",
        view_id="view-id",
        title="各建筑升级次数",
        legacy_sql_sha256=sql_fingerprint("SELECT legacy_a"),
        source_key="remaining:82f560ee39f2409485e7270d2c9db26c",
    )
    target_b = TargetView(
        dashboard_id="dashboard-id",
        view_id="view-id",
        title="各建筑升级次数",
        legacy_sql_sha256=sql_fingerprint("SELECT legacy_b"),
        source_key="remaining:82f560ee39f2409485e7270d2c9db26c",
    )
    view = {"chart": {"title": target_a.title}, "sql": legacy_sql}

    class Cursor:
        def __init__(self) -> None:
            self.executed: list[str] = []
            self.rowcount = 0

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_value, traceback):
            return False

        def execute(self, sql, params=None) -> None:
            del params
            self.executed.append(sql)
            if "UPDATE public.core_dashboard" in sql:
                self.rowcount = 1

        def fetchone(self):
            return (
                target_a.dashboard_id,
                "测试看板",
                DATASOURCE_ID,
                TENANT_ID,
                json.dumps({target_a.view_id: view}),
            )

    class Connection:
        def __init__(self) -> None:
            self.cursor_value = Cursor()

        def cursor(self):
            return self.cursor_value

    connection = Connection()
    module = sys.modules["repair_flam_first_zombie_semantic_dashboards"]
    backups: list[object] = []
    monkeypatch.setattr(
        module,
        "TARGET_VIEWS",
        (target_a, target_b),
    )
    monkeypatch.setattr(module, "_backup_dashboard", lambda *args: backups.append(args))

    result = repair_dashboards(connection, apply=apply)

    outcome = "updated" if apply else "would_update"
    assert result[outcome] == ["dashboard-id:view-id"]
    assert result["skipped_stale"] == []
    assert ("FOR UPDATE" in connection.cursor_value.executed[0]) is expects_lock
    assert len(backups) == int(apply)
