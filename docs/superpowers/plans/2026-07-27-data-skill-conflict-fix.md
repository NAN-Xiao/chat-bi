# Data Skill 冲突修复 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 消除 Skill 225/282、257/276 的 SQL 口径冲突，将 Skill 280 限定到修仙数据源 6，并把 Skill 234 合并到 171 后停用。

**Architecture:** 业务规则继续保存在数据源或平台 Data Skill 中，不向通用运行时代码硬编码业务表名。种子脚本负责可重复发布 225/257/276/282；独立治理脚本使用事务、前置摘要校验、备份和 embedding 刷新更新 171/234/280；真实运行时函数负责最终召回与 SQL 校验回归。

**Tech Stack:** Python 3.11、pytest、PostgreSQL/psycopg、SQLAlchemy、JSON Data Skill 声明、现有 embedding 服务。

## Global Constraints

- Skill 282 实时触发词精确为：`今天`、`当天`、`今日`、`实时`、`当前小时`、`当前分钟`、`当前整点`。
- `当前`、`截至目前`、`截至当前` 不得作为 Skill 282 的独立触发项。
- Skill 225 的未完成当日付费查询使用 `event_realtime`；完整历史日仍使用 `event`。
- Skill 257/276 的真实交易来源为 `ServerPayLog`；金额读取 `personal.money`，用户按 `uid` 去重，不使用 `paytotal`。
- Skill 280 保持 `USER_PRIVATE`、原租户、所有者、正文和用户偏好，只改为 `specific_ds=true, datasource_ids=[6]`。
- Skill 234 合并进 171 后设置 `active=false, visible=false`，不物理删除。
- 所有数据库写入必须先备份目标行，在一个事务中执行，并在前置状态漂移时拒绝写入。
- 不修改与本任务无关的前端文件，不推送远端分支。

---

### Task 1: 收窄 Skill 282 实时触发条件

**Files:**
- Modify: `tests/test_seed_platform_realtime_event_table_skill.py`
- Modify: `backend/tests/test_data_skill_sql_validation.py`
- Modify: `tools/seed_platform_realtime_event_table_skill.py`

**Interfaces:**
- Consumes: `SQL_VALIDATION_RULE` JSON、`_data_skill_sql_validation_violation(question, sql, data_skill)`。
- Produces: `REALTIME_TRIGGER_TERMS: tuple[str, ...]` 和不受泛化“当前”影响的 Skill 282 prompt。

- [ ] **Step 1: 写入失败测试**

在 `tests/test_seed_platform_realtime_event_table_skill.py` 解析声明并精确断言：

```python
def test_realtime_trigger_terms_are_explicit_and_narrow() -> None:
    rule = json.loads(module.SQL_VALIDATION_RULE)
    assert rule["match"] == [
        "今天", "当天", "今日", "实时", "当前小时", "当前分钟", "当前整点",
    ]
    for term in ("当前", "截至目前", "截至当前"):
        assert term not in rule["match"]
```

在 `backend/tests/test_data_skill_sql_validation.py` 增加参数化负例：

```python
import importlib
import sys
from pathlib import Path

TOOLS_DIR = Path(__file__).resolve().parents[2] / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))
platform_skill = importlib.import_module("seed_platform_realtime_event_table_skill")

@pytest.mark.parametrize("question", [
    "当前等级的活跃用户分布",
    "截至目前的历史累计付费趋势",
    "截至当前的完整历史日付费",
])
def test_generic_current_phrases_do_not_activate_realtime_rule(question: str) -> None:
    rule = json.loads(platform_skill.SQL_VALIDATION_RULE)
    data_skill = _data_skill(rule)
    sql = "SELECT COUNT(DISTINCT e.uid) FROM event e WHERE e.dt=20260726"
    assert llm._data_skill_sql_validation_violation(question, sql, data_skill) is None
```

- [ ] **Step 2: 运行 RED 测试**

Run:

```powershell
.\backend\.venv\Scripts\python.exe -m pytest tests/test_seed_platform_realtime_event_table_skill.py backend/tests/test_data_skill_sql_validation.py -q
```

Expected: 触发词精确集合断言失败，三个泛化表达至少一个错误触发实时校验。

- [ ] **Step 3: 最小实现**

在 `tools/seed_platform_realtime_event_table_skill.py` 定义并复用：

```python
REALTIME_TRIGGER_TERMS = (
    "今天", "当天", "今日", "实时", "当前小时", "当前分钟", "当前整点",
)

SQL_VALIDATION_RULE = json.dumps(
    {
        "match": list(REALTIME_TRIGGER_TERMS),
        "when_sql_patterns": [EVENT_TABLE_SCOPE_PATTERN],
        "required_sql_patterns": [REALTIME_TABLE_PATTERN],
        "forbidden_sql_patterns": [HISTORY_TABLE_PATTERN],
        "message": (
            "未完成当天的事件类查询必须使用 event_realtime，不能读取完整历史表 event；"
            "请按当前业务日分区重写 SQL。"
        ),
    },
    ensure_ascii=False,
    separators=(",", ":"),
)
```

同步重写 description 和“未完成当日”段落，只列七个保留词，并用反例说明三个删除词不能单独触发。

- [ ] **Step 4: 运行 GREEN 测试**

Run: Task 1 Step 2 的同一命令。

Expected: 全部 PASS。

- [ ] **Step 5: 提交**

```powershell
git add -- tests/test_seed_platform_realtime_event_table_skill.py backend/tests/test_data_skill_sql_validation.py tools/seed_platform_realtime_event_table_skill.py
git commit -m "修复：收窄实时事件选表触发词"
```

---

### Task 2: 统一 flam Skill 225 的实时付费 SQL

**Files:**
- Modify: `backend/tests/test_flam_first_zombie_data_skill_seed.py`
- Modify: `tools/seed_flam_first_zombie_data_skills.py`
- Modify: `tools/flam_first_zombie_dashboard_skill_overrides.json`

**Interfaces:**
- Consumes: `apply_dashboard_skill_overrides(DATA_SKILLS)`、两个 dashboard SQL ID。
- Produces: 组件 `4fc570b4be7d406c9f648d9088f760bb`、`2149b7abbc6c4cd7ad6f52379e69b15a` 的 `event_realtime` SQL 和新 SHA256。

- [ ] **Step 1: 写入失败测试**

在 `backend/tests/test_flam_first_zombie_data_skill_seed.py` 增加：

```python
@pytest.mark.parametrize("view_id", [
    "4fc570b4be7d406c9f648d9088f760bb",
    "2149b7abbc6c4cd7ad6f52379e69b15a",
])
def test_realtime_payment_components_use_realtime_event_table(view_id: str) -> None:
    sql = _seed_dashboard_sql()[view_id]
    assert "event_realtime" in sql
    assert re.search(r"\b(?:FROM|JOIN)\s+`?event`?\b", sql, re.I) is None
    assert "ServerPayLog" in sql
```

将旧 prompt 断言改为七个明确触发词，并断言不含“截至目前、当前或实时按小时”旧句。

- [ ] **Step 2: 运行 RED 测试**

Run:

```powershell
.\backend\.venv\Scripts\python.exe -m pytest backend/tests/test_flam_first_zombie_data_skill_seed.py -q
```

Expected: 两个组件仍引用 `event`，测试 FAIL。

- [ ] **Step 3: 最小实现**

在 JSON 覆盖中将两个 SQL 的事实表改为 `event_realtime`，保留 `ServerPayLog`、`prod=110000038`、UTC+8 业务日期与小时边界。同步修改 Skill 225 文案，使未完成当日查询只引用七个明确触发词。

重新计算两个 SQL 的 SHA256，并更新 `EXPECTED_CHANGED_SQL_SHA256`，不修改其他组件哈希。

- [ ] **Step 4: 运行 GREEN 测试**

Run: Task 2 Step 2 的同一命令。

Expected: 全部 PASS，哈希白名单只变化两个目标 ID。

- [ ] **Step 5: 提交**

```powershell
git add -- backend/tests/test_flam_first_zombie_data_skill_seed.py tools/seed_flam_first_zombie_data_skills.py tools/flam_first_zombie_dashboard_skill_overrides.json
git commit -m "修复：统一flam实时付费选表口径"
```

---

### Task 3: 对齐修仙 Skill 257 与 276

**Files:**
- Modify: `tests/test_seed_xiuxian_data_skills.py`
- Modify: `backend/tests/test_xiuxian_data_skill_seed.py`
- Modify: `tools/seed_xiuxian_data_skills.py`
- Modify: `tools/xiuxian_dashboard_skill_catalog.py`

**Interfaces:**
- Consumes: `SERVERPAYLOG_VALIDATION`、`build_data_skills(dashboards)`、payer-penetration topic。
- Produces: 金额与用户数分开的校验规则，以及窗口累计金额/累计用户定义。

- [ ] **Step 1: 写入失败测试**

解析 `SERVERPAYLOG_VALIDATION`，断言金额规则和人数规则互不强制无关字段：

```python
def parse_validation(marker: str) -> list[dict[str, object]]:
    payload = marker.split("data-skill-sql-validation:", 1)[1]
    payload = payload.rsplit("-->", 1)[0].strip()
    rules = json.loads(payload)
    assert isinstance(rules, list)
    return rules


def test_serverpaylog_validation_separates_amount_and_payer_count() -> None:
    rules = parse_validation(module.SERVERPAYLOG_VALIDATION)
    amount = next(rule for rule in rules if "付费金额" in rule["match"])
    payer = next(rule for rule in rules if "付费用户" in rule["match"])
    assert amount["required_sql_contains"] == ["ServerPayLog", "$.money"]
    assert payer["required_sql_contains"] == ["ServerPayLog"]
    assert payer["required_sql_patterns"] == [module.DISTINCT_UID_PATTERN]
```

对 payer-penetration prompt 断言：包含“所选窗口”“ServerPayLog.personal.money”“全窗口去重 uid”，不包含“累计 paytotal”。

- [ ] **Step 2: 运行 RED 测试**

Run:

```powershell
.\backend\.venv\Scripts\python.exe -m pytest tests/test_seed_xiuxian_data_skills.py backend/tests/test_xiuxian_data_skill_seed.py -q
```

Expected: 旧合并规则仍要求付费用户 SQL 出现 `$.money`，且目录仍描述 `paytotal`，测试 FAIL。

- [ ] **Step 3: 最小实现**

在 `tools/seed_xiuxian_data_skills.py` 定义：

```python
DISTINCT_UID_PATTERN = (
    r"COUNT\s*\(\s*DISTINCT\s+(?:`?\w+`?\s*\.\s*)?`?uid`?\s*\)"
)
```

将验证声明拆成：首日快照、交易金额、付费用户三组。交易金额匹配收入/流水/付费金额/ARPU/ARPPU并要求 `ServerPayLog + $.money`；付费用户匹配付费用户/付费人数并要求 `ServerPayLog + DISTINCT_UID_PATTERN`；两组都禁止 `PayBuyRet`、`ed_money`、`paytotal`。

更新 payer-penetration guidance：累计金额为窗口内 `SUM(personal.money)`；累计用户为窗口内 `COUNT(DISTINCT uid)`；累计趋势按首次付费用户日期生成累计去重人数，禁止累计每日去重人数。

- [ ] **Step 4: 运行 GREEN 测试**

Run: Task 3 Step 2 的同一命令。

Expected: 全部 PASS。

- [ ] **Step 5: 提交**

```powershell
git add -- tests/test_seed_xiuxian_data_skills.py backend/tests/test_xiuxian_data_skill_seed.py tools/seed_xiuxian_data_skills.py tools/xiuxian_dashboard_skill_catalog.py
git commit -m "修复：统一修仙累计付费交易口径"
```

---

### Task 4: 治理 Skill 171、234、280

**Files:**
- Create: `tools/repair_data_skill_scope_conflicts.py`
- Create: `tests/test_repair_data_skill_scope_conflicts.py`

**Interfaces:**
- Consumes: `core_system_db_config()`、`save_custom_prompt_skill_embedding(...)`。
- Produces: `repair_skills(backend: RepairBackend, apply: bool) -> RepairReport`，默认 dry-run，`--mode apply` 才写入。

- [ ] **Step 1: 写入失败测试**

使用 FakeBackend 覆盖以下契约：

```python
def test_apply_merges_234_into_171_and_scopes_280() -> None:
    backend = FakeBackend(valid_snapshots())
    report = module.repair_skills(backend, apply=True)
    assert report.updated_ids == (171, 234, 280)
    assert backend.rows[280]["specific_ds"] is True
    assert backend.rows[280]["datasource_ids"] == [6]
    assert backend.rows[234]["active"] is False
    assert backend.rows[234]["visible"] is False
    assert module.BOUNDED_SCAN_MARKER in backend.rows[171]["prompt"]
```

另测：默认 dry-run 不写入；171/234/280 任一名称、作用域或 SHA256 不匹配时整体拒绝；embedding 失败恢复三条备份；280 的 tenant/create_by/visibility/prompt 不变。

- [ ] **Step 2: 运行 RED 测试**

Run:

```powershell
.\backend\.venv\Scripts\python.exe -m pytest tests/test_repair_data_skill_scope_conflicts.py -q
```

Expected: 模块不存在，collection FAIL。

- [ ] **Step 3: 最小实现**

实现常量：

```python
EXPECTED_PROMPT_SHA256 = {
    171: "96f7fb760fb14b62cd84df9ba3a4e21da615ead3c12cc7324bceb2a5a8145c2c",
    234: "a7330d9e46175e1a991d058492a0b2d72323ef0e780a62d3e66a1320257c09ec",
    280: "3073d524631de743c6b87019cf28fd717ef4ea7314b86ff5284be082b7bd9514",
}
BOUNDED_SCAN_MARKER = "<!-- data-skill-managed-section:bounded-fact-scan:v1 -->"
```

171 追加的受管段落必须明确：仅对高成本事实明细、必须先由 Schema/元数据确认时间字段、使用用户指定或平台允许的有界时间/分区条件、不得错误阻断维表/小表/无时间字段分析。

Psycopg backend 在同一事务中 `SELECT ... FOR UPDATE` 三条记录、校验摘要、写备份 JSON、更新 171/234/280、提交，然后刷新 171/280 embedding 并回读验证；刷新失败使用备份恢复三条记录。234 停用后 embedding/signature 保持 NULL。

- [ ] **Step 4: 运行 GREEN 测试与 dry-run**

Run:

```powershell
.\backend\.venv\Scripts\python.exe -m pytest tests/test_repair_data_skill_scope_conflicts.py -q
.\backend\.venv\Scripts\python.exe tools/repair_data_skill_scope_conflicts.py
```

Expected: pytest PASS；dry-run 输出目标 171/234/280 且 `updated=false`，数据库无变化。

- [ ] **Step 5: 提交**

```powershell
git add -- tools/repair_data_skill_scope_conflicts.py tests/test_repair_data_skill_scope_conflicts.py
git commit -m "修复：治理Data Skill数据源作用域"
```

---

### Task 5: 四问题集成回归、发布与回读

**Files:**
- Create: `backend/tests/test_data_skill_conflict_regressions.py`
- Modify only if testability requires: `backend/apps/chat/curd/custom_prompt.py`

**Interfaces:**
- Consumes: `find_data_skills(...)`、`_data_skill_sql_validation_violation(...)`、四个发布脚本。
- Produces: 四个固定问题的实际上下文与 SQL 校验证据，以及数据库发布回读报告。

- [ ] **Step 1: 写入四场景失败测试**

使用真实 seed prompt 构造 FakeSession 行，并调用真实 `find_data_skills`。固定场景：

```python
SCENARIOS = (
    (3, "今天实时付费趋势", {225, 282}),
    (6, "按渠道统计累计付费用户数", {257, 276, 282}),
    (6, "统计昨天的付费用户数", {257, 282}),
    (6, "当前等级的活跃用户分布", {255, 278, 282}),
)
```

每个场景断言 234 不存在；flam 场景断言 280 不存在。随后将 Skill 上下文传给真实校验器，使用设计文档中的四条合规 SQL，断言返回 `None`；并保留一条冲突前 SQL 断言确实返回违规。

- [ ] **Step 2: 运行完整 RED/GREEN 集成测试**

Run:

```powershell
.\backend\.venv\Scripts\python.exe -m pytest backend/tests/test_data_skill_conflict_regressions.py -q
```

Expected: 在前四个 Task 完成后直接 PASS；若 FAIL，只修复配置拼接或测试 fixture，不在通用运行时代码加入业务特判。

- [ ] **Step 3: 运行定向测试门禁**

Run:

```powershell
.\backend\.venv\Scripts\python.exe -m pytest tests/test_seed_platform_realtime_event_table_skill.py backend/tests/test_data_skill_sql_validation.py backend/tests/test_flam_first_zombie_data_skill_seed.py tests/test_seed_xiuxian_data_skills.py backend/tests/test_xiuxian_data_skill_seed.py tests/test_repair_data_skill_scope_conflicts.py backend/tests/test_data_skill_conflict_regressions.py -q
```

Expected: 全部 PASS。

- [ ] **Step 4: 发布配置**

先执行只读预检，再依次发布，任一步失败立即停止后续写入：

```powershell
.\backend\.venv\Scripts\python.exe tools/seed_platform_realtime_event_table_skill.py --mode dry-run
.\backend\.venv\Scripts\python.exe tools/repair_data_skill_scope_conflicts.py
.\backend\.venv\Scripts\python.exe tools/seed_platform_realtime_event_table_skill.py --mode apply
.\backend\.venv\Scripts\python.exe tools/seed_flam_first_zombie_data_skills.py
.\backend\.venv\Scripts\python.exe tools/publish_xiuxian_dashboard_data_skills.py --mode apply
.\backend\.venv\Scripts\python.exe tools/repair_data_skill_scope_conflicts.py --mode apply
```

Expected: 225/257/276/282 原 ID 被幂等更新；171/234/280 通过 CAS 治理；embedding 刷新成功。

- [ ] **Step 5: 数据库回读与真实召回验证**

使用只读 SQL 回读 171、225、234、257、276、280、282 的 `active/visible/visibility_scope/specific_ds/datasource_ids/prompt/embedding_signature`。再用当前系统库 Session 调用 `find_data_skills` 重放四个问题和 Skill 280 的跨数据源问题，最后将合规 SQL 传给 `_data_skill_sql_validation_violation`。

Expected:

- 280 仅数据源 6 可见，原 tenant/create_by/prompt 不变。
- 234 inactive 且 invisible，embedding/signature 为 NULL。
- 171 包含唯一受管段落并有新 embedding signature。
- 四个问题的上下文包含设计要求的 Skill，234 均缺席，SQL 校验均为 PASS。
- Skill 280 所有者在数据源 6 的资源问题可召回，在数据源 3/1 不可召回。

- [ ] **Step 6: 提交集成测试与最终检查**

```powershell
git add -- backend/tests/test_data_skill_conflict_regressions.py
git diff --cached --check
git commit -m "测试：覆盖Data Skill冲突召回组合"
git status --short
```

Expected: 提交仅包含本任务文件；工作区没有意外修改。不执行 `git push`。
