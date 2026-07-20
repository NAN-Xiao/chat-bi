from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[1]
TOOLS_DIR = ROOT / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

module = importlib.import_module("sync_xiuxian_active_payer_rate_skill")


CURRENT_SQL = """
WITH user_day_flags AS (
    SELECT e.dt, e.uid,
           MAX(CASE WHEN e.event = 'UserActive' THEN 1 ELSE 0 END) AS is_active,
           MAX(CASE WHEN e.event = 'ServerPayLog' THEN 1 ELSE 0 END) AS is_payer
    FROM `event` e
    WHERE e.dt BETWEEN
              CAST(DATE_FORMAT(DATE_SUB(CURDATE(), INTERVAL 15 DAY), '%Y%m%d') AS SIGNED)
          AND CAST(DATE_FORMAT(DATE_SUB(CURDATE(), INTERVAL 1 DAY), '%Y%m%d') AS SIGNED)
      AND e.prod = 110000047
      AND e.event IN ('UserActive', 'ServerPayLog')
    GROUP BY e.dt, e.uid
)
SELECT STR_TO_DATE(CAST(dt AS CHAR), '%Y%m%d') AS `日期`,
       SUM(is_active) AS `活跃用户数`,
       SUM(CASE WHEN is_active = 1 AND is_payer = 1 THEN 1 ELSE 0 END) AS `活跃付费用户数`,
       ROUND(SUM(CASE WHEN is_active = 1 AND is_payer = 1 THEN 1 ELSE 0 END)
             / NULLIF(SUM(is_active), 0) * 100, 2) AS `活跃用户付费率`
FROM user_day_flags
WHERE is_active = 1
GROUP BY dt
ORDER BY dt;
""".strip()


def target_view_fixture() -> dict:
    return {
        "id": module.VIEW_ID,
        "datasource": module.DATASOURCE_ID,
        "fields": ["日期", "累计付费率"],
        "sql": CURRENT_SQL,
        "chart": {
            "title": module.TITLE,
            "xAxis": [{"value": "日期"}],
            "yAxis": [{"value": "活跃用户付费率"}],
        },
        "sourceConfig": {
            "sql": {
                "datasource": module.DATASOURCE_ID,
                "sql": CURRENT_SQL,
                "builder": {"timeRange": "30d"},
            }
        },
    }


def test_normalize_target_view_replaces_stale_fields_and_builder():
    source = target_view_fixture()

    normalized = module.normalize_target_view(source)

    assert normalized["fields"] == [
        "日期",
        "活跃用户数",
        "活跃付费用户数",
        "活跃用户付费率",
    ]
    assert normalized["chart"]["title"] == module.TITLE
    assert normalized["chart"]["xAxis"] == [{"value": "日期"}]
    assert normalized["chart"]["yAxis"] == [
        {
            "value": "活跃用户付费率",
            "metricType": "ratio",
            "pivotAggregation": "avg",
        }
    ]
    assert "builder" not in normalized["sourceConfig"]["sql"]
    assert normalized["sql"] == normalized["sourceConfig"]["sql"]["sql"]
    assert source["fields"] == ["日期", "累计付费率"]


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda view: view.update(datasource=3), "datasource 6"),
        (
            lambda view: view.update(sql=view["sql"].replace("110000047", "110000038")),
            "旧口径",
        ),
        (
            lambda view: view.update(sql=view["sql"].replace("INTERVAL 15 DAY", "INTERVAL 14 DAY")),
            "权威口径",
        ),
        (
            lambda view: view.update(sql=view["sql"].replace("ServerPayLog", "PayBuyRet")),
            "权威口径",
        ),
        (
            lambda view: view.update(sql=view["sql"].replace("`活跃用户付费率`", "`累计付费率`")),
            "旧口径",
        ),
    ],
    ids=("datasource", "product", "window", "events", "legacy-field"),
)
def test_normalize_target_view_rejects_non_authoritative_sql(mutate, message):
    view = target_view_fixture()
    mutate(view)
    view["sourceConfig"]["sql"]["sql"] = view["sql"]

    with pytest.raises(ValueError, match=message):
        module.normalize_target_view(view)


def test_normalize_target_view_rejects_divergent_source_sql():
    view = target_view_fixture()
    view["sourceConfig"]["sql"]["sql"] += "\n"

    with pytest.raises(ValueError, match="不一致"):
        module.normalize_target_view(view)


def test_normalize_target_view_returns_deep_copy():
    source = target_view_fixture()
    normalized = module.normalize_target_view(source)

    normalized["chart"]["title"] = "changed"

    assert source["chart"]["title"] == module.TITLE


def dashboard_row_fixture():
    canvas = {
        module.VIEW_ID: target_view_fixture(),
        "other-view": {
            "id": "other-view",
            "datasource": module.DATASOURCE_ID,
            "fields": ["日期", "其他指标"],
            "sql": "SELECT 1",
        },
    }
    return (
        module.DASHBOARD_ID,
        "核心看板",
        module.TENANT_ID,
        module.DATASOURCE_ID,
        json.dumps(canvas, ensure_ascii=False, separators=(",", ":")),
        1784533028,
    )


def test_dashboard_source_from_row_preserves_original_and_normalizes_target():
    source = module.dashboard_source_from_row(dashboard_row_fixture(), skill_id=276)

    original = json.loads(source.original_canvas)
    normalized = json.loads(source.normalized_canvas)
    assert source.skill_id == 276
    assert source.sql == CURRENT_SQL
    assert original[module.VIEW_ID]["fields"] == ["日期", "累计付费率"]
    assert normalized[module.VIEW_ID]["fields"] == list(module.FIELDS)
    assert "builder" not in normalized[module.VIEW_ID]["sourceConfig"]["sql"]
    assert normalized["other-view"] == original["other-view"]


def test_dashboard_source_from_row_rejects_missing_target_view():
    row = list(dashboard_row_fixture())
    canvas = json.loads(row[4])
    del canvas[module.VIEW_ID]
    row[4] = json.dumps(canvas, ensure_ascii=False)

    with pytest.raises(ValueError, match="目标组件"):
        module.dashboard_source_from_row(tuple(row), skill_id=276)


def test_build_target_skill_requires_only_payer_penetration_components():
    from xiuxian_dashboard_skill_catalog import TOPICS
    from xiuxian_dashboard_snapshot import DashboardSnapshot

    topic = next(item for item in TOPICS if item.slug == "payer-penetration")
    canvas = {
        view_id: {
            "id": view_id,
            "datasource": module.DATASOURCE_ID,
            "fields": ["日期", "指标"],
            "sql": CURRENT_SQL if view_id == module.VIEW_ID else f"SELECT '{view_id}' AS id",
        }
        for view_id in topic.view_ids
    }
    dashboards = [
        DashboardSnapshot.from_row(
            (
                module.DASHBOARD_ID,
                "核心看板",
                module.TENANT_ID,
                module.DATASOURCE_ID,
                json.dumps(canvas, ensure_ascii=False),
            )
        )
    ]

    skill = module.build_target_skill(dashboards)

    assert skill["prompt"].startswith(module.SKILL_MARKER)
    assert skill["prompt"].count("<!-- dashboard-sql:") == 6
    assert "活跃用户付费率" in skill["prompt"]


def test_target_dashboard_backup_is_signed_and_detects_tampering(tmp_path):
    source = module.dashboard_source_from_row(dashboard_row_fixture(), skill_id=276)

    backup_path = module.write_target_dashboard_backup(source, tmp_path, "backup-1")

    assert module.verify_target_dashboard_backup(backup_path) == source
    assert {path.name for path in backup_path.iterdir()} == {
        "dashboard.json",
        "manifest.json",
    }

    (backup_path / "dashboard.json").write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="哈希"):
        module.verify_target_dashboard_backup(backup_path)


def generated_skill(sql: str = CURRENT_SQL) -> dict[str, str]:
    return {
        "name": "修仙付费用户、渗透与累计付费",
        "description": "付费用户、渗透率与累计金额。",
        "prompt": (
            f"{module.SKILL_MARKER}\n"
            "# 修仙付费用户、渗透与累计付费\n"
            "近15日活跃用户付费率按天计算，分母为 UserActive 去重 uid，"
            "分子为当天同时存在 UserActive 和 ServerPayLog 的去重 uid。\n\n"
            f"<!-- dashboard-sql:{module.VIEW_ID} -->\n```sql\n{sql}\n```"
        ),
    }


def source_fixture():
    return SimpleNamespace(sql=CURRENT_SQL, skill_id=276)


def test_validate_skill_source_requires_one_byte_identical_sql_block():
    source = source_fixture()

    module.validate_skill_source(generated_skill(), source)

    with pytest.raises(ValueError, match="不一致"):
        module.validate_skill_source(generated_skill(CURRENT_SQL + "\n"), source)


class FakeBackend:
    def __init__(self):
        self.calls: list[str] = []
        self.source = source_fixture()
        self.skill = generated_skill()
        self.other_hashes = {269: ("prompt-a", "embedding-a")}
        self.fail_at = ""

    def load(self):
        self.calls.append("load")
        return self.source

    def build(self, source):
        assert source is self.source
        self.calls.append("build")
        return self.skill

    def load_other_hashes(self):
        self.calls.append("hashes")
        return self.other_hashes

    def backup(self, source, skill):
        assert source is self.source and skill is self.skill
        self.calls.append("backup")
        return Path("backup/active-payer-rate")

    def lock(self):
        self.calls.append("lock")

    def assert_unchanged(self, source):
        assert source is self.source
        self.calls.append("reload")
        if self.fail_at == "cas":
            raise module.SourceDashboardChangedError("CAS conflict")

    def update_dashboard(self, source):
        assert source is self.source
        self.calls.append("update-dashboard")

    def upsert_skill(self, skill):
        assert skill is self.skill
        self.calls.append("upsert-skill")
        return 276

    def refresh_embedding(self, skill_id):
        assert skill_id == 276
        self.calls.append("embedding")
        if self.fail_at == "embedding":
            raise RuntimeError("embedding failed")

    def verify(self, source, skill, skill_id):
        assert source is self.source and skill is self.skill and skill_id == 276
        self.calls.append("verify")

    def verify_other_hashes(self, baseline):
        assert baseline is self.other_hashes
        self.calls.append("other-hashes")

    def retrieve(self, question):
        assert question == module.RETRIEVAL_QUESTION
        self.calls.append("retrieve")
        if self.fail_at == "retrieve":
            return "未命中"
        return "修仙付费用户、渗透与累计付费 UserActive ServerPayLog 活跃用户付费率"

    def restore(self):
        self.calls.append("restore")

    def unlock(self):
        self.calls.append("unlock")


def test_sync_dry_run_never_writes():
    backend = FakeBackend()

    report = module.sync_active_payer_rate(backend, apply=False)

    assert backend.calls == ["load", "build", "hashes", "backup"]
    assert report.mode == "dry-run"
    assert report.skill_id == 276
    assert report.updated is False
    assert Path(report.backup_path) == Path("backup/active-payer-rate")


def test_sync_apply_updates_dashboard_then_only_target_skill():
    backend = FakeBackend()

    report = module.sync_active_payer_rate(backend, apply=True)

    assert backend.calls == [
        "load",
        "build",
        "hashes",
        "backup",
        "lock",
        "reload",
        "update-dashboard",
        "upsert-skill",
        "embedding",
        "verify",
        "other-hashes",
        "retrieve",
        "unlock",
    ]
    assert report.mode == "apply"
    assert report.skill_id == 276
    assert report.updated is True
    assert report.embedding_verified is True
    assert report.retrieval_verified is True


def test_sync_cas_conflict_stops_before_write_without_restore():
    backend = FakeBackend()
    backend.fail_at = "cas"

    with pytest.raises(module.SourceDashboardChangedError, match="CAS conflict"):
        module.sync_active_payer_rate(backend, apply=True)

    assert backend.calls[-3:] == ["lock", "reload", "unlock"]
    assert "update-dashboard" not in backend.calls
    assert "restore" not in backend.calls


def test_sync_embedding_failure_restores_dashboard_and_skill():
    backend = FakeBackend()
    backend.fail_at = "embedding"

    with pytest.raises(RuntimeError, match="embedding failed"):
        module.sync_active_payer_rate(backend, apply=True)

    assert backend.calls[-2:] == ["restore", "unlock"]


def test_sync_retrieval_failure_restores_dashboard_and_skill():
    backend = FakeBackend()
    backend.fail_at = "retrieve"

    with pytest.raises(module.RetrievalVerificationError, match="缺少"):
        module.sync_active_payer_rate(backend, apply=True)

    assert backend.calls[-2:] == ["restore", "unlock"]
