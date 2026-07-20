# 修仙活跃用户付费率看板与 Data Skill 同步实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将修仙 datasource 6 核心看板的近15日活跃用户付费率配置与 `payer-penetration` Data Skill 定向同步，并保证后续全量发布不会恢复旧累计口径。

**Architecture:** 业务规则继续由主题目录维护，SQL 继续以推荐看板当前配置为权威来源。新增定向同步入口，在同一发布锁下完成组件元数据 CAS 更新、单 Skill 生成与 upsert，并复用现有备份、恢复、Embedding 和检索能力；旧累计 SQL 从日期边界自动改写白名单移除。

**Tech Stack:** Python 3、pytest、psycopg 3、PostgreSQL JSONB、现有修仙 Data Skill 生成器与 Embedding 发布工具。

## Global Constraints

- 仅适用于 tenant `7482727237662281728`、datasource `6`、产品 `110000047`。
- 仅修改看板 `afe201c9762c448aa0495f3508c01793` 的组件 `95d8497afac14f0a90342031fb43bc04`。
- 仅更新 source marker `data-skill-source:xiuxian:dashboard:payer-penetration` 对应 Skill。
- 时间范围固定为昨天减 14 天至昨天，共 15 个完整自然日，不做时区处理。
- 活跃付费用户必须同时存在 `UserActive` 和 `ServerPayLog`；分母为当天 `UserActive` 去重用户。
- 不使用旧字段“累计付费率”，不使用 `user.pay.paytotal` 作为该指标来源。
- 其他 12 条修仙 Data Skill 的 Prompt 和 Embedding 签名必须保持不变。
- 所有数据库写入前必须生成可校验备份；CAS、Embedding 或回读失败时恢复看板与目标 Skill。

---

### Task 1: 固化活跃用户付费率主题口径

**Files:**
- Modify: `tests/test_seed_xiuxian_data_skills.py`
- Modify: `tools/xiuxian_dashboard_skill_catalog.py:115`

**Interfaces:**
- Consumes: `TOPICS: tuple[TopicDefinition, ...]`。
- Produces: `payer-penetration` 主题规则，供 `build_data_skills()` 写入目标 Prompt。

- [ ] **Step 1: 写失败测试**

在 `tests/test_seed_xiuxian_data_skills.py` 增加：

```python
def test_payer_penetration_topic_defines_active_payer_rate_contract():
    topic = next(item for item in catalog.TOPICS if item.slug == "payer-penetration")

    assert "活跃用户付费率" in topic.rule
    assert "UserActive" in topic.rule
    assert "ServerPayLog" in topic.rule
    assert "同时" in topic.rule
    assert "每日" in topic.rule
    assert "不是累计付费率" in topic.rule
    assert "paytotal" in topic.rule
```

- [ ] **Step 2: 运行测试确认失败**

Run: `backend\.venv\Scripts\python.exe -m pytest tests/test_seed_xiuxian_data_skills.py::test_payer_penetration_topic_defines_active_payer_rate_contract -q`

Expected: FAIL，旧规则只声明日付费用户和累计 `paytotal`。

- [ ] **Step 3: 最小修改主题规则**

把 `payer-penetration` 的规则改为：

```python
(
    "日付费用户按 ServerPayLog.uid 去重；近15日活跃用户付费率按天计算，"
    "分母为 UserActive 去重 uid，分子为当天同时存在 UserActive 和 "
    "ServerPayLog 的去重 uid；这是每日比率，不是累计付费率。"
    "累计 paytotal 只用于明确的累计快照指标，不能作为活跃用户付费率来源。"
)
```

- [ ] **Step 4: 运行主题生成测试**

Run: `backend\.venv\Scripts\python.exe -m pytest tests/test_seed_xiuxian_data_skills.py -q`

Expected: PASS。

- [ ] **Step 5: 提交**

```powershell
git add -- tools/xiuxian_dashboard_skill_catalog.py tests/test_seed_xiuxian_data_skills.py
git commit -m "修复：明确修仙活跃用户付费率口径"
```

### Task 2: 退休目标组件的旧累计 SQL 自动改写

**Files:**
- Modify: `tests/test_xiuxian_dashboard_sql_repair.py`
- Modify: `tests/test_publish_xiuxian_dashboard_data_skills.py`
- Modify: `tools/xiuxian_dashboard_sql_repair.py:35`
- Modify: `tools/publish_xiuxian_dashboard_data_skills.py:63`

**Interfaces:**
- Consumes: `REPAIR_SOURCE_HASHES`、`REPAIR_REWRITTEN_HASHES`、`REPAIR_SPECS`。
- Produces: 10 条仍需日期边界修复的目录；目标组件 SQL 原样进入 Skill 生成流程。

- [ ] **Step 1: 写失败测试**

增加以下断言，并把发布器假数据数量改为从 `EXPECTED_REPAIR_COUNT` 读取：

```python
def test_active_payer_rate_is_not_in_legacy_bounds_repair_catalog():
    assert "95d8497afac14f0a90342031fb43bc04" not in repair.REPAIR_SPECS
    assert len(repair.REPAIR_SPECS) == 10


def test_expected_repair_count_tracks_audited_catalog():
    assert publisher.EXPECTED_REPAIR_COUNT == len(repair.REPAIR_SPECS) == 10
```

将测试内硬编码的 `range(11)`、`"11_equivalence"`、`"11_explain"` 和 `== 11`
改为使用 `publisher.EXPECTED_REPAIR_COUNT` 构造期望值。

- [ ] **Step 2: 运行测试确认失败**

Run: `backend\.venv\Scripts\python.exe -m pytest tests/test_xiuxian_dashboard_sql_repair.py tests/test_publish_xiuxian_dashboard_data_skills.py -q`

Expected: FAIL，目标 view 仍在 11 条旧累计 SQL 白名单中。

- [ ] **Step 3: 删除两份旧哈希并动态计算数量**

从 `REPAIR_SOURCE_HASHES` 和 `REPAIR_REWRITTEN_HASHES` 删除键：

```python
"95d8497afac14f0a90342031fb43bc04"
```

在发布器中改为：

```python
EXPECTED_REPAIR_COUNT = len(REPAIR_SPECS)
```

同时把错误信息中的固定“11 条”统一改为：

```python
f"{EXPECTED_REPAIR_COUNT} 条修复目录"
```

文档字符串统一使用不含固定数字的“完整修复目录”。

- [ ] **Step 4: 运行修复与发布器测试**

Run: `backend\.venv\Scripts\python.exe -m pytest tests/test_xiuxian_dashboard_sql_repair.py tests/test_publish_xiuxian_dashboard_data_skills.py -q`

Expected: PASS，修复目录为 10 条。

- [ ] **Step 5: 提交**

```powershell
git add -- tools/xiuxian_dashboard_sql_repair.py tools/publish_xiuxian_dashboard_data_skills.py tests/test_xiuxian_dashboard_sql_repair.py tests/test_publish_xiuxian_dashboard_data_skills.py
git commit -m "修复：退休活跃付费率旧SQL改写"
```

### Task 3: 实现单组件与单 Skill 定向同步

**Files:**
- Create: `tools/sync_xiuxian_active_payer_rate_skill.py`
- Create: `tests/test_sync_xiuxian_active_payer_rate_skill.py`

**Interfaces:**
- Produces: `normalize_target_view(view: Mapping[str, Any]) -> dict[str, Any]`。
- Produces: `sync_active_payer_rate(backend: Any, *, apply: bool) -> SyncReport`。
- Consumes: `build_data_skills()`、`backup_existing_skills()`、`upsert_skills()`、`refresh_and_verify_embeddings()`。

- [ ] **Step 1: 写纯函数失败测试**

```python
def test_normalize_target_view_replaces_stale_fields_and_builder():
    source = target_view_fixture()
    source["fields"] = ["日期", "累计付费率"]
    source["sourceConfig"]["sql"]["builder"] = {"timeRange": "30d"}

    normalized = module.normalize_target_view(source)

    assert normalized["fields"] == [
        "日期", "活跃用户数", "活跃付费用户数", "活跃用户付费率"
    ]
    assert normalized["chart"]["title"] == "近15日活跃用户付费率趋势"
    assert normalized["chart"]["xAxis"] == [{"value": "日期"}]
    assert normalized["chart"]["yAxis"] == [{
        "value": "活跃用户付费率",
        "metricType": "ratio",
        "pivotAggregation": "avg",
    }]
    assert "builder" not in normalized["sourceConfig"]["sql"]
    assert normalized["sql"] == normalized["sourceConfig"]["sql"]["sql"]
```

再增加拒绝错误 datasource、错误产品、非15天范围、缺失双事件和旧输出字段的参数化测试。

- [ ] **Step 2: 运行纯函数测试确认失败**

Run: `backend\.venv\Scripts\python.exe -m pytest tests/test_sync_xiuxian_active_payer_rate_skill.py -q`

Expected: ERROR，模块尚不存在。

- [ ] **Step 3: 实现常量、校验和标准化函数**

新模块至少定义：

```python
TENANT_ID = 7482727237662281728
DATASOURCE_ID = 6
DASHBOARD_ID = "afe201c9762c448aa0495f3508c01793"
VIEW_ID = "95d8497afac14f0a90342031fb43bc04"
SKILL_MARKER = "<!-- data-skill-source:xiuxian:dashboard:payer-penetration -->"
TITLE = "近15日活跃用户付费率趋势"
FIELDS = ("日期", "活跃用户数", "活跃付费用户数", "活跃用户付费率")
RETRIEVAL_QUESTION = "近15日活跃用户付费率趋势"


def validate_target_sql(sql: str) -> None:
    required = (
        "INTERVAL 15 DAY", "INTERVAL 1 DAY", "e.prod = 110000047",
        "UserActive", "ServerPayLog", "`活跃用户数`",
        "`活跃付费用户数`", "`活跃用户付费率`",
    )
    missing = [value for value in required if value not in sql]
    if missing:
        raise ValueError(f"活跃用户付费率 SQL 缺少权威口径: {missing}")
    forbidden = ("110000038", "`累计付费率`", "$.paytotal")
    found = [value for value in forbidden if value in sql]
    if found:
        raise ValueError(f"活跃用户付费率 SQL 包含旧口径: {found}")


def normalize_target_view(view: Mapping[str, Any]) -> dict[str, Any]:
    normalized = copy.deepcopy(dict(view))
    sql = str(normalized.get("sql") or "").strip()
    validate_target_sql(sql)
    if int(normalized.get("datasource")) != DATASOURCE_ID:
        raise ValueError("目标组件不属于修仙 datasource 6")
    normalized["fields"] = list(FIELDS)
    chart = normalized.setdefault("chart", {})
    chart["title"] = TITLE
    chart["xAxis"] = [{"value": "日期"}]
    chart["yAxis"] = [{
        "value": "活跃用户付费率",
        "metricType": "ratio",
        "pivotAggregation": "avg",
    }]
    sql_config = normalized.setdefault("sourceConfig", {}).setdefault("sql", {})
    if str(sql_config.get("sql") or "").strip() != sql:
        raise ValueError("目标组件直接 SQL 与 sourceConfig SQL 不一致")
    sql_config.pop("builder", None)
    return normalized
```

- [ ] **Step 4: 写同步编排失败测试**

使用记录调用顺序的 `FakeBackend` 覆盖：dry-run 无写入、apply 顺序、CAS 冲突、
Embedding 失败恢复看板与 Skill、其他 12 条 Prompt 哈希不变、检索未命中失败。

核心顺序断言：

```python
assert backend.calls == [
    "load", "build", "hashes", "backup", "lock", "reload",
    "update-dashboard", "upsert-skill", "embedding", "verify",
    "other-hashes", "retrieve", "unlock",
]
```

- [ ] **Step 5: 实现定向编排与 psycopg 后端**

实现 `SyncReport`、异常类型和 `sync_active_payer_rate()`；复用
`sync_xiuxian_realtime_payment_skill.py` 已验证的发布锁、恢复连接、Skill 备份、
Embedding 与检索实现。与实时脚本不同之处必须显式实现：

```python
def sync_active_payer_rate(backend: Any, *, apply: bool) -> SyncReport:
    source = backend.load()
    skill = backend.build(source)
    hashes = backend.load_other_hashes()
    backup_path = backend.backup(source, skill)
    if not apply:
        return SyncReport("dry-run", backup_path, False, False, False)
    backend.lock()
    try:
        backend.assert_unchanged(source)
        backend.update_dashboard(source)
        skill_id = backend.upsert_skill(skill)
        backend.refresh_embedding(skill_id)
        backend.verify(source, skill, skill_id)
        backend.verify_other_hashes(hashes)
        backend.verify_retrieval(RETRIEVAL_QUESTION)
    except BaseException:
        backend.restore(source, skill)
        raise
    finally:
        backend.unlock()
    return SyncReport("apply", backup_path, True, True, True)
```

`PsycopgBackend.update_dashboard()` 必须使用：

```sql
UPDATE core_dashboard
SET canvas_view_info = %s,
    update_time = %s
WHERE id = %s
  AND tenant_id = %s
  AND datasource = %s
  AND canvas_view_info = %s
  AND update_time = %s
```

并要求 `rowcount == 1`。`upsert_skill()` 只向 `upsert_skills()` 传入一个 Skill；
发布前后对其余 12 条 Skill 的 `(id, prompt_sha256, embedding_signature)` 做完全比较。

- [ ] **Step 6: 运行定向同步单测**

Run: `backend\.venv\Scripts\python.exe -m pytest tests/test_sync_xiuxian_active_payer_rate_skill.py -q`

Expected: PASS。

- [ ] **Step 7: 运行修仙发布相关回归**

Run: `backend\.venv\Scripts\python.exe -m pytest tests/test_seed_xiuxian_data_skills.py tests/test_xiuxian_dashboard_sql_repair.py tests/test_publish_xiuxian_dashboard_data_skills.py tests/test_sync_xiuxian_active_payer_rate_skill.py tests/test_sync_xiuxian_realtime_payment_skill.py -q`

Expected: PASS。

- [ ] **Step 8: 提交**

```powershell
git add -- tools/sync_xiuxian_active_payer_rate_skill.py tests/test_sync_xiuxian_active_payer_rate_skill.py
git commit -m "功能：定向同步修仙活跃付费率技能"
```

### Task 4: Dry-run、线上应用与回读验证

**Files:**
- Runtime backup: `.codex-runtime/xiuxian-active-payer-rate-skill-backups/`

**Interfaces:**
- Consumes: Task 3 的 CLI `--mode dry-run|apply`。
- Produces: 同步报告、看板备份、Skill 恢复工件和线上验证证据。

- [ ] **Step 1: 执行 dry-run**

Run:

```powershell
backend\.venv\Scripts\python.exe tools\sync_xiuxian_active_payer_rate_skill.py --mode dry-run
```

Expected: `updated=false`，输出唯一组件、唯一 Skill、备份路径和新 Prompt 哈希。

- [ ] **Step 2: 核对 dry-run 备份与 SQL**

验证备份存在且可解析；执行目标 SQL并记录 15 行、字段和耗时。当前基准为约 `0.8 秒`，
但验收只要求小于应用的 60 秒超时。

- [ ] **Step 3: 执行 apply**

Run:

```powershell
backend\.venv\Scripts\python.exe tools\sync_xiuxian_active_payer_rate_skill.py --mode apply
```

Expected: `updated=true`、`embedding_verified=true`、`retrieval_verified=true`。

- [ ] **Step 4: 独立回读数据库**

核对：

```text
dashboard.fields = 日期,活跃用户数,活跃付费用户数,活跃用户付费率
dashboard.chart.yAxis = 活跃用户付费率
dashboard.sourceConfig.sql.builder 不存在
skill marker 唯一
skill SQL == dashboard SQL
其他 12 条 Prompt SHA-256 和 embedding_signature 未变化
```

- [ ] **Step 5: 运行最终回归和格式检查**

Run:

```powershell
backend\.venv\Scripts\python.exe -m pytest tests/test_seed_xiuxian_data_skills.py tests/test_xiuxian_dashboard_sql_repair.py tests/test_publish_xiuxian_dashboard_data_skills.py tests/test_sync_xiuxian_active_payer_rate_skill.py tests/test_sync_xiuxian_realtime_payment_skill.py -q
git diff --check
git status --short
```

Expected: 测试全部 PASS，`git diff --check` 无输出，只保留本任务文件和用户原有未跟踪目录。
