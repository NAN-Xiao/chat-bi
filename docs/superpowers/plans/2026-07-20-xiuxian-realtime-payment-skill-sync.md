# 修仙实时付费 Data Skill 定向同步实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将修仙实时看板当前组件 `2193936101973073920` 的每小时支付记录数与收入金额口径持久同步到现有 Data Skill `269`，且不写入其他 Skills 或看板。

**Architecture:** 先更新推荐看板组件目录与快照数量契约，使生成器能够从当前 9 个看板、44 个组件构建稳定内容；再增加 marker 限定的定向同步入口，只对 `data-skill-source:xiuxian:dashboard:realtime-payment` 执行备份、CAS 校验、幂等更新、embedding 刷新和召回验证。线上执行前后都重新读取看板与 Skill，任何漂移或验证失败均中止并恢复 Skill 269。

**Tech Stack:** Python 3.11、pytest、psycopg 3、PostgreSQL、现有 `custom_prompt` Data Skill 与 embedding 服务。

## Global Constraints

- 仅处理 `tenant_id=7482727237662281728`、`datasource_id=6`。
- 保留 Skill ID `269`、名称 `修仙实时付费趋势`、现有 source marker 和 `ADMIN_PUBLIC` 工作空间作用域。
- 当前看板 SQL 是唯一 SQL 来源；不得修改看板 SQL，不得自行改写日期、时区或产品条件。
- 当前业务口径固定为 `event_realtime`、`ServerPayLog`、`COUNT(*)` 和 `personal.money` 汇总。
- 其他 12 个修仙 Skills 不得写入；现有未关联工作区改动不得暂存或提交。
- Git 提交信息使用中文。

---

### Task 1: 更新当前推荐看板目录契约

**Files:**
- Modify: `tools/xiuxian_dashboard_skill_catalog.py:22-31`
- Modify: `tools/xiuxian_dashboard_skill_catalog.py:164-210`
- Modify: `tools/xiuxian_dashboard_snapshot.py:19-21`
- Modify: `tests/test_seed_xiuxian_data_skills.py:99-116`
- Modify: `tests/test_xiuxian_dashboard_snapshot.py:26-88`

**Interfaces:**
- Consumes: 当前实时看板组件 ID `2193936101973073920` 及 `DashboardSnapshot.drawers`。
- Produces: `TOPICS` 中只含当前实时组件的 `realtime-payment` 定义，以及 9 看板、44 组件、44 个非空 SQL 的快照契约。

- [ ] **Step 1: 写入目录变化的失败测试**

```python
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
```

- [ ] **Step 2: 运行测试并确认因旧目录失败**

Run: `backend\.venv\Scripts\python.exe -m pytest tests/test_seed_xiuxian_data_skills.py tests/test_xiuxian_dashboard_snapshot.py -q`

Expected: FAIL，显示 `realtime-payment` 仍包含两个旧组件或快照仍要求 45 个组件。

- [ ] **Step 3: 最小更新目录和快照常量**

```python
TopicDefinition(
    "realtime-payment",
    "修仙实时付费趋势",
    "实时每小时支付记录数与收入金额。",
    ("2193936101973073920",),
    "event_realtime 的 ServerPayLog 按小时统计支付记录数，并汇总 personal.money 为收入金额。",
)

EXPECTED_DRAWER_COUNT = 44
EXPECTED_NONEMPTY_DRAWER_COUNT = 44
```

同步将生成 SQL 块总数断言从 `44` 调整为 `43`；保留已知 `EMPTY_DASHBOARD_VIEW_ID` 的既有过滤规则，不借本任务改变其他主题。

- [ ] **Step 4: 运行目录与快照测试**

Run: `backend\.venv\Scripts\python.exe -m pytest tests/test_seed_xiuxian_data_skills.py tests/test_xiuxian_dashboard_snapshot.py -q`

Expected: PASS。

- [ ] **Step 5: 提交目录契约**

```powershell
git add -- tools/xiuxian_dashboard_skill_catalog.py tools/xiuxian_dashboard_snapshot.py tests/test_seed_xiuxian_data_skills.py tests/test_xiuxian_dashboard_snapshot.py
git commit -m "修复：同步修仙实时付费组件目录"
```

### Task 2: 增加单 Skill 安全同步入口

**Files:**
- Create: `tools/sync_xiuxian_realtime_payment_skill.py`
- Create: `tests/test_sync_xiuxian_realtime_payment_skill.py`

**Interfaces:**
- Consumes: `load_recommended_dashboards(connection) -> list[DashboardSnapshot]`、`build_data_skills(dashboards) -> list[dict[str, str]]`、`upsert_skills(cursor, skills) -> list[int]`、`backup_existing_skills`、`restore_published_skills`、`refresh_and_verify_embeddings`。
- Produces: `build_realtime_skill(dashboards) -> dict[str, str]`、`sync_realtime_skill(connection_factory, *, apply: bool) -> SyncReport`，只允许目标 marker 和 Skill ID `269`。

- [ ] **Step 1: 写入失败测试，覆盖目标提取和拒绝漂移**

```python
def test_build_realtime_skill_selects_only_current_marker_and_sql():
    skill = module.build_realtime_skill(current_dashboard_snapshots())
    assert skill["prompt"].startswith(module.REALTIME_SKILL_MARKER)
    assert skill["prompt"].count("<!-- dashboard-sql:") == 1
    assert module.REALTIME_VIEW_ID in skill["prompt"]


def test_sync_rejects_changed_dashboard_before_skill_write():
    factory = changing_dashboard_connection_factory()
    with pytest.raises(module.SourceDashboardChangedError):
        module.sync_realtime_skill(factory, apply=True)
    assert factory.skill_updates == []


def test_sync_writes_only_skill_269():
    factory = stable_connection_factory()
    report = module.sync_realtime_skill(factory, apply=True)
    assert report.skill_id == 269
    assert factory.updated_skill_ids == [269]
```

测试文件同时提供 `stable_connection_factory()` 和 `changing_dashboard_connection_factory()`；二者复用仓库既有 `_FakeCursor` 风格记录 SQL 与参数，前者对两次来源读取返回相同 `update_time`/SQL 摘要，后者在第二次读取返回不同摘要，并暴露 `skill_updates`、`updated_skill_ids`、`embedding_ids` 和 `restored_skill_ids` 供断言。

- [ ] **Step 2: 运行新测试并确认模块缺失**

Run: `backend\.venv\Scripts\python.exe -m pytest tests/test_sync_xiuxian_realtime_payment_skill.py -q`

Expected: FAIL，显示无法导入 `sync_xiuxian_realtime_payment_skill`。

- [ ] **Step 3: 实现只读构建与来源守卫**

```python
REALTIME_DASHBOARD_ID = "10604280d5a941af9720800bce6e030f"
REALTIME_VIEW_ID = "2193936101973073920"
REALTIME_SKILL_MARKER = "<!-- data-skill-source:xiuxian:dashboard:realtime-payment -->"
EXPECTED_SKILL_ID = 269


def build_realtime_skill(dashboards):
    skills = build_data_skills(dashboards)
    matches = [skill for skill in skills if skill["prompt"].startswith(REALTIME_SKILL_MARKER)]
    if len(matches) != 1:
        raise RuntimeError("实时付费 Skill marker 必须唯一")
    return matches[0]
```

来源守卫必须比较目标看板 ID、租户、数据源、组件 ID、SQL SHA-256 和 `update_time`；获取发布锁后再次读取并比较，变化即抛出 `SourceDashboardChangedError`。

- [ ] **Step 4: 实现定向备份、写入、embedding 与恢复**

定向写入流程必须按以下顺序执行：获取现有 Skill 269 完整快照及用户偏好；确认 marker 唯一且命中 ID 269；调用 `upsert_skills(cursor, [skill])`；只校验返回 `[269]`、作用域字段、prompt 字节一致和 embedding 字段已清空；提交；只为 `[269]` 刷新并验证 embedding。任一步失败时，使用已捕获期望态进行 CAS 恢复，不得操作其他 marker。

- [ ] **Step 5: 添加 dry-run、恢复和召回测试**

```python
def test_dry_run_never_updates_skill_or_embedding():
    factory = stable_connection_factory()
    report = module.sync_realtime_skill(factory, apply=False)
    assert report.updated is False
    assert factory.updated_skill_ids == []
    assert factory.embedding_ids == []


def test_embedding_failure_restores_skill_269_only():
    factory = stable_connection_factory(embedding_error=RuntimeError("embedding failed"))
    with pytest.raises(RuntimeError, match="embedding failed"):
        module.sync_realtime_skill(factory, apply=True)
    assert factory.restored_skill_ids == [269]


def test_duplicate_realtime_marker_is_rejected():
    factory = stable_connection_factory(skill_ids=[269, 280])
    with pytest.raises(RuntimeError, match="marker 重复"):
        module.sync_realtime_skill(factory, apply=True)
    assert factory.updated_skill_ids == []


def test_retrieval_finds_realtime_skill_for_hourly_payment_and_revenue():
    factory = stable_connection_factory(retrieved_skill_ids=[269])
    report = module.sync_realtime_skill(factory, apply=True)
    assert report.retrieval_verified is True
    assert "event_realtime" in report.prompt
    assert "ServerPayLog" in report.prompt
    assert "$.money" in report.prompt
```

召回问题固定为“今天每小时支付记录数和收入金额”，期望首选或入选 `修仙实时付费趋势`，返回内容必须含 `event_realtime`、`ServerPayLog` 和 `$.money`。

- [ ] **Step 6: 运行定向同步与既有发布回归测试**

Run: `backend\.venv\Scripts\python.exe -m pytest tests/test_sync_xiuxian_realtime_payment_skill.py tests/test_seed_xiuxian_data_skills.py tests/test_xiuxian_dashboard_snapshot.py tests/test_publish_xiuxian_dashboard_data_skills.py -q`

Expected: PASS。

- [ ] **Step 7: 提交定向同步入口**

```powershell
git add -- tools/sync_xiuxian_realtime_payment_skill.py tests/test_sync_xiuxian_realtime_payment_skill.py
git commit -m "功能：支持修仙实时付费 Skill 定向同步"
```

### Task 3: 执行线上定向同步并验证

**Files:**
- Runtime backup: `.codex-runtime/xiuxian-realtime-payment-skill-backups/<timestamp>/`
- No source file changes expected.

**Interfaces:**
- Consumes: `sync_xiuxian_realtime_payment_skill.py --mode dry-run|apply`。
- Produces: Skill 269 的已验证新版本、备份目录和同步报告。

- [ ] **Step 1: 执行 dry-run 并核对来源**

Run: `backend\.venv\Scripts\python.exe tools\sync_xiuxian_realtime_payment_skill.py --mode dry-run`

Expected: 输出 dashboard `10604280d5a941af9720800bce6e030f`、view `2193936101973073920`、Skill `269`、当前 SQL SHA-256；报告 `updates=0`。

- [ ] **Step 2: 执行 apply**

Run: `backend\.venv\Scripts\python.exe tools\sync_xiuxian_realtime_payment_skill.py --mode apply`

Expected: 输出 `skill_id=269`、`updated=1`、`embedding_verified=1`、备份路径和召回成功；没有其他 Skill ID。

- [ ] **Step 3: 独立只读核验数据库状态**

使用仓库虚拟环境和 `psycopg` 查询 `custom_prompt`：确认 ID、作用域、marker、组件 ID、SQL SHA-256、旧组件缺失、embedding 非空及签名正确；再查询 13 个修仙 marker 的 prompt 哈希，除 ID 269 外均与 apply 前一致。

- [ ] **Step 4: 运行最终回归与差异检查**

Run: `backend\.venv\Scripts\python.exe -m pytest tests/test_sync_xiuxian_realtime_payment_skill.py tests/test_seed_xiuxian_data_skills.py tests/test_xiuxian_dashboard_snapshot.py tests/test_publish_xiuxian_dashboard_data_skills.py backend/tests/test_xiuxian_data_skill_seed.py -q`

Run: `backend\.venv\Scripts\python.exe -m ruff check tools/sync_xiuxian_realtime_payment_skill.py tools/xiuxian_dashboard_skill_catalog.py tools/xiuxian_dashboard_snapshot.py tests/test_sync_xiuxian_realtime_payment_skill.py tests/test_seed_xiuxian_data_skills.py tests/test_xiuxian_dashboard_snapshot.py`

Run: `git diff --check`

Expected: 全部通过；工作树只保留本任务文件和用户原有未跟踪内容。
