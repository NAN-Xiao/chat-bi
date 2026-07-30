from __future__ import annotations

import importlib.util
import json
import runpy
import sys
import types
from contextlib import nullcontext
from dataclasses import replace
from datetime import datetime
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SEED_SCRIPT = ROOT / "tools" / "seed_xiuxian_data_skills.py"


def _load_seed_module():
    if not SEED_SCRIPT.exists():
        pytest.fail("缺少修仙 Data Skill 种子脚本")
    tools_path = str(ROOT / "tools")
    if tools_path not in sys.path:
        sys.path.insert(0, tools_path)
    spec = importlib.util.spec_from_file_location("seed_xiuxian_data_skills", SEED_SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_payer_penetration_topic_defines_active_payer_rate_contract():
    _load_seed_module()
    from xiuxian_dashboard_skill_catalog import TOPICS

    topic = next(item for item in TOPICS if item.slug == "payer-penetration")

    assert "活跃用户付费率" in topic.guidance
    assert "UserActive" in topic.guidance
    assert "ServerPayLog" in topic.guidance
    assert "同时" in topic.guidance
    assert "每日" in topic.guidance
    assert "不是累计付费率" in topic.guidance
    assert "所选时间窗口" in topic.guidance
    assert "SUM(ServerPayLog.personal.money)" in topic.guidance
    assert "COUNT(DISTINCT ServerPayLog.uid)" in topic.guidance
    assert "累计每日去重人数" in topic.guidance
    assert "paytotal" not in topic.guidance


def test_new_user_retention_topic_excludes_immature_d7_cohorts() -> None:
    _load_seed_module()
    from xiuxian_dashboard_skill_catalog import TOPICS

    topic = next(item for item in TOPICS if item.slug == "new-user-retention")

    assert "D7" in topic.guidance
    assert "至少 7 个完整自然日" in topic.guidance
    assert "未成熟 cohort 不得进入分母" in topic.guidance
    assert "样本数" in topic.guidance
    assert "成熟 cohort" in topic.guidance
    assert "{{dashboard_end_yyyymmdd}}" in topic.guidance
    assert "INTERVAL 7 DAY" in topic.guidance
    assert "e.dt <=" in topic.guidance


def _parse_serverpaylog_validation(module) -> list[dict[str, object]]:
    payload = module.SERVERPAYLOG_VALIDATION.split(
        "data-skill-sql-validation:", 1
    )[1].rsplit("-->", 1)[0].strip()
    rules = json.loads(payload)
    assert isinstance(rules, list)
    return rules


def test_serverpaylog_validation_separates_amount_and_payer_count():
    module = _load_seed_module()
    rules = _parse_serverpaylog_validation(module)

    amount = next(rule for rule in rules if "付费金额" in rule["match"])
    payer = next(rule for rule in rules if "付费用户" in rule["match"])

    assert amount["required_sql_contains"] == ["ServerPayLog", "$.money"]
    assert payer["required_sql_contains"] == ["ServerPayLog"]
    assert payer["required_sql_patterns"] == [module.DISTINCT_UID_PATTERN]
    assert "personal.money" not in payer["message"]
    assert "按 uid 去重" in payer["message"]


def test_xiuxian_date_partition_skill_is_scoped_and_actionable():
    module = _load_seed_module()

    assert module.TENANT_ID == 7482727237662281728
    assert module.DATASOURCE_ID == 6
    assert len(module.DATA_SKILLS) >= 1

    skill = next(
        skill
        for skill in module.DATA_SKILLS
        if "data-skill-source:xiuxian:date-partition-aggregation" in skill["prompt"]
    )
    prompt = skill["prompt"]
    assert prompt.lstrip().startswith(
        "<!-- data-skill-source:xiuxian:date-partition-aggregation -->"
    )
    assert "`dt` 是 `YYYYMMDD` 格式的整数业务日期分区字段" in prompt
    assert "WHERE e.dt BETWEEN" in prompt
    assert "GROUP BY e.dt" in prompt
    assert "ORDER BY e.dt" in prompt
    assert "STR_TO_DATE(CAST(e.dt AS CHAR), '%Y%m%d')" in prompt
    assert "'%Y-%m-%d'" in prompt
    assert "AS dt" in prompt
    assert "SELECT MAX(" not in prompt.upper()
    assert "## 标准聚合 SQL" not in prompt
    assert "## 日期窗口规则" in prompt
    assert "用户指定绝对起止日期" in prompt
    assert "用户指定相对日期窗口" in prompt
    assert "未指定日期窗口时，默认查询截至昨天的最近 28 个自然日" in prompt
    assert "29 天是示例参数，不表示固定查询范围" in prompt
    assert "DATE_SUB(CURDATE(), INTERVAL 29 DAY)" in prompt
    assert "DATE_SUB(CURDATE(), INTERVAL 1 DAY)" in prompt
    assert "AS start_dt" not in prompt


def _dashboard_snapshots(module):
    from xiuxian_dashboard_skill_catalog import EXPECTED_VIEW_IDS
    from xiuxian_dashboard_snapshot import DashboardSnapshot

    view_ids = sorted(EXPECTED_VIEW_IDS)
    dashboards = []
    for dashboard_index in range(9):
        canvas = {}
        for offset, view_id in enumerate(
            view_ids[dashboard_index * 5 : dashboard_index * 5 + 5]
        ):
            index = dashboard_index * 5 + offset
            canvas[view_id] = {
                "id": view_id,
                "sql": f"SELECT {index} AS metric_{index}",
                "chart": {"title": f"组件 {index}"},
            }
        dashboards.append(
            DashboardSnapshot.from_row(
                (
                    f"dashboard-{dashboard_index}",
                    f"推荐看板 {dashboard_index}",
                    module.TENANT_ID,
                    module.DATASOURCE_ID,
                    json.dumps(canvas, ensure_ascii=False),
                )
            )
        )
    return dashboards


def test_build_data_skills_produces_one_base_and_twelve_topics():
    module = _load_seed_module()

    skills = module.build_data_skills(_dashboard_snapshots(module))
    prompts = [skill["prompt"] for skill in skills]

    assert len(skills) == 13
    assert sum(prompt.count("<!-- dashboard-sql:") for prompt in prompts) == (
        43 - len(module.PAYER_PROMPT_EXCLUDED_VIEW_IDS)
    )
    assert all("1e4e34743f2d47dfa1c2948742b93a50" not in prompt for prompt in prompts)
    assert all(len(prompt) <= 15_000 for prompt in prompts)
    assert len({prompt.splitlines()[0] for prompt in prompts}) == 13
    assert any(
        prompt.startswith(
            "<!-- data-skill-source:xiuxian:serverpaylog-monetization-arppu -->"
        )
        for prompt in prompts
    )
    assert all("datasource_id=6" in prompt for prompt in prompts)


def test_realtime_payment_topic_uses_current_single_dashboard_view():
    module = _load_seed_module()
    topic = next(item for item in module.TOPICS if item.slug == "realtime-payment")

    assert topic.view_ids == ("2193936101973073920",)
    assert "支付记录数" in topic.guidance
    assert "收入金额" in topic.guidance


def test_build_data_skills_embeds_current_realtime_dashboard_sql_once():
    module = _load_seed_module()
    skills = module.build_data_skills(_dashboard_snapshots(module))
    skill = next(item for item in skills if item["name"] == "修仙实时付费趋势")

    assert skill["prompt"].count("<!-- dashboard-sql:") == 1
    assert "<!-- dashboard-sql:2193936101973073920 -->" in skill["prompt"]
    assert "eafa54818ed54020a16369a42c99783f" not in skill["prompt"]
    assert "d093ae51d20942ffa69bfcea7a14f740" not in skill["prompt"]


def test_new_user_retention_is_a_strong_keyword_candidate_for_channel_d1_question(
    monkeypatch,
):
    module = _load_seed_module()
    backend_path = str(ROOT / "backend")
    monkeypatch.syspath_prepend(backend_path)
    from apps.chat.curd import custom_prompt as custom_prompt_runtime
    from apps.chat.curd.custom_prompt_embedding import skill_definition_signature

    question = "各渠道新增用户次日留存"
    original_selector = custom_prompt_runtime._select_ranked_data_skills

    class QueryEmbeddingModel:
        @staticmethod
        def embed_query(_text):
            return [1.0, 0.0]

    def build_and_rank(topics):
        monkeypatch.setattr(module, "TOPICS", topics)
        skills = module.build_data_skills(_dashboard_snapshots(module))
        rows = []
        for index, skill in enumerate(skills, start=1):
            rows.append(
                {
                    "id": index,
                    **skill,
                    "visibility_scope": "ADMIN_PUBLIC",
                    "embedding": [1.0, 0.0],
                    "embedding_signature": skill_definition_signature(
                        skill["name"],
                        skill["description"],
                        skill["prompt"],
                        dim=2,
                    ),
                }
            )
        embedding_names = {
            "修仙渠道新增与投放获客",
            "修仙新增用户总量与系统归因",
        }
        selector_calls = 0

        def select_embedding_then_keywords(scored, skill_rows):
            nonlocal selector_calls
            selector_calls += 1
            if selector_calls == 1:
                return [row for row in skill_rows if row["name"] in embedding_names]
            return original_selector(scored, skill_rows)

        monkeypatch.setattr(
            custom_prompt_runtime,
            "_select_ranked_data_skills",
            select_embedding_then_keywords,
        )
        monkeypatch.setattr(custom_prompt_runtime.settings, "EMBEDDING_ENABLED", True)
        monkeypatch.setattr(
            custom_prompt_runtime.EmbeddingModelCache,
            "get_model",
            lambda: QueryEmbeddingModel(),
        )
        selected = custom_prompt_runtime._rank_auto_data_skills_by_embedding(
            rows,
            question,
        )
        retention = next(row for row in rows if row["name"] == "修仙新增 cohort 留存")
        return (
            {row["name"] for row in selected},
            custom_prompt_runtime._score_data_skill(retention, question),
        )

    old_topics = tuple(
        replace(topic, description="新增 cohort D1/D3/D7 留存。")
        if topic.slug == "new-user-retention"
        else topic
        for topic in module.TOPICS
    )
    old_selected, old_score = build_and_rank(old_topics)
    current_selected, current_score = build_and_rank(
        importlib.import_module("xiuxian_dashboard_skill_catalog").TOPICS
    )

    assert "修仙新增 cohort 留存" not in old_selected
    assert "修仙新增 cohort 留存" in current_selected
    assert current_score > old_score


def test_build_data_skills_fails_closed_when_a_dashboard_view_is_missing():
    module = _load_seed_module()
    dashboards = _dashboard_snapshots(module)
    first = dashboards[0]
    canvas = json.loads(first.canvas_view_info)
    canvas.pop(next(iter(canvas)))
    from xiuxian_dashboard_snapshot import DashboardSnapshot

    dashboards[0] = DashboardSnapshot.from_row(
        (
            first.id,
            first.name,
            first.tenant_id,
            first.datasource,
            json.dumps(canvas, ensure_ascii=False),
        )
    )

    with pytest.raises(ValueError, match="view|抽屉|目录"):
        module.build_data_skills(dashboards)


def test_build_data_skills_ignores_the_known_empty_dashboard_view():
    module = _load_seed_module()
    dashboards = _dashboard_snapshots(module)
    from xiuxian_dashboard_snapshot import DashboardSnapshot

    for index, dashboard in enumerate(dashboards):
        canvas = json.loads(dashboard.canvas_view_info)
        if module.EMPTY_DASHBOARD_VIEW_ID not in canvas:
            continue
        canvas[module.EMPTY_DASHBOARD_VIEW_ID]["sql"] = ""
        dashboards[index] = DashboardSnapshot.from_row(
            (
                dashboard.id,
                dashboard.name,
                dashboard.tenant_id,
                dashboard.datasource,
                json.dumps(canvas, ensure_ascii=False),
            )
        )
        break

    skills = module.build_data_skills(dashboards)

    assert sum(skill["prompt"].count("<!-- dashboard-sql:") for skill in skills) == (
        43 - len(module.PAYER_PROMPT_EXCLUDED_VIEW_IDS)
    )


class _FakeCursor:
    def __init__(self):
        self.skill_id = None
        self.fetchone_result = None
        self.rowcount = 0
        self.statements: list[str] = []
        self.calls: list[tuple[str, object]] = []

    def execute(self, sql, params=None):
        normalized = " ".join(str(sql).split())
        self.statements.append(normalized)
        self.calls.append((normalized, params))
        self.rowcount = 0
        if "pg_advisory_xact_lock" in normalized:
            self.fetchone_result = (None,)
        elif normalized.startswith("SELECT id FROM custom_prompt"):
            self.fetchone_result = (self.skill_id,) if self.skill_id is not None else None
        elif normalized.startswith("INSERT INTO custom_prompt"):
            self.skill_id = 255
            self.fetchone_result = (self.skill_id,)
            self.rowcount = 1
        elif normalized.startswith("UPDATE custom_prompt"):
            self.fetchone_result = None
            self.rowcount = 1

    def fetchone(self):
        return self.fetchone_result

    def fetchall(self):
        return [self.fetchone_result] if self.fetchone_result is not None else []


class _FakeConnection:
    def __init__(self):
        self.cursor_instance = _FakeCursor()
        self.committed = False
        self.rolled_back = False

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def cursor(self):
        return nullcontext(self.cursor_instance)

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True


def test_upsert_is_serialized_and_reuses_the_existing_record():
    module = _load_seed_module()
    cursor = _FakeCursor()
    now = datetime(2026, 7, 15, 14, 0, 0)

    first_id = module._upsert_skill(cursor, skill=module.DATA_SKILLS[0], now=now)
    second_id = module._upsert_skill(cursor, skill=module.DATA_SKILLS[0], now=now)

    assert first_id == second_id == 255
    assert sum("pg_advisory_xact_lock" in sql for sql in cursor.statements) == 2
    assert sum(sql.startswith("INSERT INTO custom_prompt") for sql in cursor.statements) == 1
    assert sum(sql.startswith("UPDATE custom_prompt") for sql in cursor.statements) == 1
    written_sql = " ".join(cursor.statements)
    assert "visibility_scope = 'ADMIN_PUBLIC'" in written_sql
    assert "specific_ds = TRUE" in written_sql
    assert "active = TRUE" in written_sql


def test_upsert_skills_exposes_the_batch_interface():
    module = _load_seed_module()
    cursor = _FakeCursor()

    ids = module.upsert_skills(
        cursor,
        [module.DATA_SKILLS[0]],
        now=datetime(2026, 7, 16, 12, 0, 0),
    )

    assert ids == [255]


def test_serverpaylog_upsert_migrates_legacy_marker_in_place():
    module = _load_seed_module()
    skill = next(
        item
        for item in module.build_data_skills(_dashboard_snapshots(module))
        if item["prompt"].startswith(module.SERVERPAYLOG_MARKER)
    )

    class LegacyCursor(_FakeCursor):
        def execute(self, sql, params=None):
            normalized = " ".join(str(sql).split())
            self.statements.append(normalized)
            self.rowcount = 0
            if "pg_advisory_xact_lock" in normalized:
                self.fetchone_result = (None,)
            elif normalized.startswith("SELECT id FROM custom_prompt"):
                marker = params[2]
                self.fetchone_result = (
                    (777,) if marker == module.LEGACY_PAYMENT_MARKER else None
                )
            elif normalized.startswith("UPDATE custom_prompt"):
                self.fetchone_result = None
                self.rowcount = 1

    cursor = LegacyCursor()

    skill_id = module._upsert_skill(
        cursor,
        skill=skill,
        now=datetime(2026, 7, 16, 12, 0, 0),
    )

    assert skill_id == 777
    assert sum(sql.startswith("SELECT id FROM custom_prompt") for sql in cursor.statements) == 2
    assert sum(sql.startswith("UPDATE custom_prompt") for sql in cursor.statements) == 1
    assert module.LEGACY_PAYMENT_MARKER not in skill["prompt"]


def test_upsert_fails_closed_when_current_marker_is_duplicated():
    module = _load_seed_module()

    class DuplicateCursor(_FakeCursor):
        def fetchall(self):
            return [(7,), (8,)]

    with pytest.raises(RuntimeError, match="marker.*重复|重复.*marker"):
        module._upsert_skill(
            DuplicateCursor(),
            skill=module.DATA_SKILLS[0],
            now=datetime(2026, 7, 16, 12, 0, 0),
        )


def test_serverpaylog_upsert_fails_when_current_and_legacy_markers_coexist():
    module = _load_seed_module()
    skill = next(
        item
        for item in module.build_data_skills(_dashboard_snapshots(module))
        if item["prompt"].startswith(module.SERVERPAYLOG_MARKER)
    )

    class CoexistingCursor(_FakeCursor):
        def execute(self, sql, params=None):
            normalized = " ".join(str(sql).split())
            self.statements.append(normalized)
            self.calls.append((normalized, params))
            self.rowcount = 0
            if "pg_advisory_xact_lock" in normalized:
                self.fetchone_result = (None,)
            elif normalized.startswith("SELECT id FROM custom_prompt"):
                self.fetchone_result = (
                    (7,) if params[2] == module.SERVERPAYLOG_MARKER else (8,)
                )

    with pytest.raises(RuntimeError, match="ServerPayLog.*legacy|legacy.*ServerPayLog"):
        module._upsert_skill(
            CoexistingCursor(),
            skill=skill,
            now=datetime(2026, 7, 16, 12, 0, 0),
        )


def test_backup_skills_includes_user_preferences():
    module = _load_seed_module()

    class SnapshotCursor:
        def __init__(self):
            self.statements = []
            self._rows = []

        def execute(self, sql, params=None):
            normalized = " ".join(str(sql).split())
            self.statements.append((normalized, params))
            if "SELECT to_jsonb(cp)" in normalized:
                self._rows = [
                    (
                        {
                            "id": 7,
                            "tenant_id": module.TENANT_ID,
                            "name": "旧 Skill",
                            "prompt": "旧 Prompt",
                            "datasource_ids": [module.DATASOURCE_ID],
                        },
                    )
                ]
            elif "SELECT to_jsonb(pref)" in normalized:
                self._rows = [
                    (
                        {
                            "id": 9,
                            "tenant_id": module.TENANT_ID,
                            "custom_prompt_id": 7,
                            "user_id": 11,
                            "enabled": False,
                        },
                    )
                ]
            else:
                self._rows = []

        def fetchall(self):
            return self._rows

    cursor = SnapshotCursor()
    backup = module.backup_existing_skills(cursor, ["marker-a", "marker-b"])

    assert backup["skills"][0]["id"] == 7
    assert backup["preferences"][0]["custom_prompt_id"] == 7

def test_verify_embeddings_checks_vector_dimension_and_signature():
    module = _load_seed_module()

    class EmbeddingCursor:
        def __init__(self):
            self.sql = ""

        def execute(self, sql, _params=None):
            self.sql = " ".join(str(sql).split())

        def fetchall(self):
            return [(7, "名称", "描述", "Prompt", "[0.1, 0.2]", "expected")]

    calls = []

    def signature(name, description, prompt, model, dim):
        calls.append((name, description, prompt, model, dim))
        return "expected"

    cursor = EmbeddingCursor()
    module.verify_embeddings(
        cursor,
        [7],
        model="embedding-model",
        signature_factory=signature,
    )

    assert calls == [("名称", "描述", "Prompt", "embedding-model", 2)]
    assert "type = 'DATA_SKILL'" in cursor.sql
    assert "specific_ds = TRUE" in cursor.sql
    assert "datasource_ids = %s::jsonb" in cursor.sql
    assert "active = TRUE" in cursor.sql
    assert "visible = TRUE" in cursor.sql
    assert "visibility_scope = 'ADMIN_PUBLIC'" in cursor.sql


def test_verify_embeddings_rejects_missing_vector():
    module = _load_seed_module()

    class EmbeddingCursor:
        def execute(self, _sql, _params=None):
            pass

        def fetchall(self):
            return [(7, "名称", "描述", "Prompt", None, None)]

    with pytest.raises(RuntimeError, match="embedding"):
        module.verify_embeddings(
            EmbeddingCursor(),
            [7],
            model=object(),
            signature_factory=lambda *_args: "expected",
        )


def test_main_delegates_exclusively_to_formal_publisher_apply_cli(monkeypatch):
    module = _load_seed_module()
    observed = []
    fake_publisher = types.ModuleType("publish_xiuxian_dashboard_data_skills")
    fake_publisher.main = lambda argv: observed.append(list(argv)) or 23
    monkeypatch.setitem(sys.modules, fake_publisher.__name__, fake_publisher)
    assert module.main(["--backup-root", "backup-dir"]) == 23
    assert observed == [["--backup-root", "backup-dir", "--mode", "apply"]]


def test_seed_cli_forwards_real_sys_argv_to_publisher_apply(monkeypatch):
    observed = []
    fake_publisher = types.ModuleType("publish_xiuxian_dashboard_data_skills")
    fake_publisher.main = lambda argv: observed.append(list(argv)) or 0
    monkeypatch.setitem(sys.modules, fake_publisher.__name__, fake_publisher)
    monkeypatch.setattr(
        sys,
        "argv",
        [str(SEED_SCRIPT), "--backup-root", "backup-dir"],
    )

    with pytest.raises(SystemExit) as exc_info:
        runpy.run_path(str(SEED_SCRIPT), run_name="__main__")

    assert exc_info.value.code == 0
    assert observed == [["--backup-root", "backup-dir", "--mode", "apply"]]


def test_seed_cli_rejects_user_supplied_mode_before_publisher(monkeypatch):
    observed = []
    fake_publisher = types.ModuleType("publish_xiuxian_dashboard_data_skills")
    fake_publisher.main = lambda argv: observed.append(list(argv)) or 0
    monkeypatch.setitem(sys.modules, fake_publisher.__name__, fake_publisher)
    monkeypatch.setattr(
        sys,
        "argv",
        [str(SEED_SCRIPT), "--mode", "dry-run"],
    )

    with pytest.raises(SystemExit, match="mode|apply"):
        runpy.run_path(str(SEED_SCRIPT), run_name="__main__")

    assert observed == []


def test_seed_cli_forwards_unknown_argument_to_publisher_parser(monkeypatch):
    publisher = __import__("publish_xiuxian_dashboard_data_skills")
    monkeypatch.setattr(
        publisher,
        "run_publish",
        lambda **_kwargs: pytest.fail("未知参数必须在运行发布前被拒绝"),
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [str(SEED_SCRIPT), "--unknown-xiuxian-option"],
    )

    with pytest.raises(SystemExit) as exc_info:
        runpy.run_path(str(SEED_SCRIPT), run_name="__main__")

    assert exc_info.value.code == 2


@pytest.mark.parametrize(
    "mode_args",
    (["--mod", "dry-run"], ["--m=dry-run"]),
)
def test_seed_cli_rejects_abbreviated_mode_arguments(monkeypatch, mode_args):
    publisher = __import__("publish_xiuxian_dashboard_data_skills")
    monkeypatch.setattr(
        publisher,
        "run_publish",
        lambda **_kwargs: pytest.fail("缩写 mode 参数必须在运行发布前被拒绝"),
    )
    monkeypatch.setattr(sys, "argv", [str(SEED_SCRIPT), *mode_args])

    with pytest.raises(SystemExit) as exc_info:
        runpy.run_path(str(SEED_SCRIPT), run_name="__main__")

    assert exc_info.value.code == 2
