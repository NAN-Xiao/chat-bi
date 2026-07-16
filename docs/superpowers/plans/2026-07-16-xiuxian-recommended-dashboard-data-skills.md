# 修仙推荐看板 Data Skills Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 先完整备份修仙推荐看板全部抽屉 SQL，在证明 11 条日期边界 SQL 结果等价后完成看板修复，再把当前 45 个非空组件拆成 12 个主题 Data Skill，发布到 datasource 6 并刷新 embedding。

**Architecture:** 用显式 view id 目录和当前 SQL SHA-256 白名单锁定处理范围；备份、AST 改写、结果等价比较、执行计划检查、系统库 compare-and-set 更新和 Skill 发布彼此独立。统一发布器默认 dry-run，只有备份与全部验证通过后才允许 apply；embedding 不完整时恢复 Skill 记录。

**Tech Stack:** Python 3.11、psycopg 3、PyMySQL、sqlglot、SQLAlchemy/SQLModel、pytest、PostgreSQL 系统库、修仙 ADS/MySQL 数据源、现有 `save_custom_prompt_skill_embedding`。

## Global Constraints

- 只处理 tenant `7482727237662281728` 和 datasource `6`，不得影响其他工作空间或数据源。
- 任何 SQL 改写、结果验证、系统库更新或 Skill 发布前，必须备份 9 个推荐看板、45 个抽屉 SQL 和完整 `canvas_view_info`。
- 备份必须验证为 9 个看板、45 个抽屉、45 个非空抽屉，且所有文件、SQL 和 manifest SHA-256 正确；失败时立即终止。
- 真实交易以 `ServerPayLog` 为准：金额 `personal.money`、订单 `personal.orderId`、商品 `personal.productid`、用户 `uid`。
- `PayBuyRet` 只允许用于支付流程/结果事件分布，不得作为收入、真实订单数、付费人数、ARPU 或 ARPPU 主来源。
- 修复 SQL 只能改变日期边界提供方式；字段、事件、JSON 路径、业务 JOIN、聚合、分组、排序、LIMIT 和图表绑定保持不变。
- 原 SQL 与改写 SQL 必须在冻结的同一 `CURDATE()` 下字段、行数和所有值等价；任一失败则整批停止。
- 每个读取 `event` 或 `user` 的大表别名直接限制 `dt`；禁止日期 `bounds` CTE 关联大表和 `MAX(dt)` 探测。
- 45 个非空 view id 必须全部且仅归属一个主题；`1e4e34743f2d47dfa1c2948742b93a50` 归入订单、礼包、月卡与支付流程主题。
- 12 个看板主题 Skill 每个最多 6 个 `dashboard-sql` 块，Prompt 不超过 15,000 字符；不得静默截断。
- 最终必须有 13 条修仙 Skill：1 条共享日期基础 Skill和 12 条看板主题 Skill。
- 实施时先用 `using-git-worktrees` 创建隔离 worktree；不要触碰当前工作区中用户已有的其他修改。

---

## File Structure

- Create `tools/xiuxian_dashboard_skill_catalog.py`: 主题定义、45 个 view id 唯一映射、Skill 文本边界和旧 marker 迁移信息。
- Create `tools/xiuxian_dashboard_snapshot.py`: 从系统库读取推荐看板、生成并校验 9/45/45 强制备份。
- Create `tools/xiuxian_dashboard_sql_repair.py`: 11 条 SQL 白名单、受限 AST 改写、冻结日期、结果比较、EXPLAIN 门禁和 compare-and-set 更新。
- Modify `tools/seed_xiuxian_data_skills.py`: 从目录和看板快照生成 13 条 Skill、迁移付费 marker、幂等 upsert、恢复和 embedding 校验。
- Create `tools/publish_xiuxian_dashboard_data_skills.py`: dry-run/apply 编排入口，确保备份、验证、更新和发布顺序不可绕过。
- Create `tests/test_xiuxian_dashboard_skill_catalog.py`: 映射完整性、唯一性、体积和主题语义测试。
- Create `tests/test_xiuxian_dashboard_snapshot.py`: 备份内容、数量、哈希、不可覆盖和失败关闭测试。
- Create `tests/test_xiuxian_dashboard_sql_repair.py`: AST 改写、等价比较、日期冻结、执行计划和 CAS 更新测试。
- Create `tests/test_publish_xiuxian_dashboard_data_skills.py`: 编排顺序、dry-run、apply 和失败恢复测试。
- Modify `tests/test_seed_xiuxian_data_skills.py`: 13 条 Skill 构建、旧 marker 迁移、upsert 和 embedding 失败测试。
- Modify `backend/tests/test_xiuxian_data_skill_seed.py`: 将 PayBuyRet 收入口径回归测试改为 ServerPayLog，并保留日期 SQL 校验测试。

---

### Task 1: 建立 45 个组件的唯一主题目录

**Files:**
- Create: `tools/xiuxian_dashboard_skill_catalog.py`
- Test: `tests/test_xiuxian_dashboard_skill_catalog.py`

**Interfaces:**
- Produces: `TopicDefinition(slug, name, description, view_ids, guidance)`、`TOPICS`、`EXPECTED_VIEW_IDS`、`validate_catalog()`。
- Consumes: 无；后续 Skill 生成器只依赖这里的显式映射，不按标题猜测。

- [ ] **Step 1: 写失败测试，锁定主题数、组件数和唯一性**

```python
def test_catalog_maps_all_nonempty_views_once():
    mapped = [view_id for topic in catalog.TOPICS for view_id in topic.view_ids]
    assert len(catalog.TOPICS) == 12
    assert len(mapped) == 45
    assert len(set(mapped)) == 45
    assert set(mapped) == catalog.EXPECTED_VIEW_IDS
    assert "1e4e34743f2d47dfa1c2948742b93a50" in mapped


def test_catalog_enforces_topic_size():
    catalog.validate_catalog()
    assert all(len(topic.view_ids) <= 6 for topic in catalog.TOPICS)
```

- [ ] **Step 2: 运行测试并确认因目录模块不存在而失败**

Run: `backend\.venv\Scripts\python.exe -m pytest tests/test_xiuxian_dashboard_skill_catalog.py -q`

Expected: FAIL，提示无法导入 `xiuxian_dashboard_skill_catalog`。

- [ ] **Step 3: 实现目录数据结构和精确映射**

```python
@dataclass(frozen=True)
class TopicDefinition:
    slug: str
    name: str
    description: str
    view_ids: tuple[str, ...]
    guidance: str


MAX_SQL_BLOCKS_PER_SKILL = 6
MAX_PROMPT_CHARS = 15_000

TOPICS = (
    TopicDefinition("realtime-payment", "修仙实时付费趋势", "实时与累计付费事件趋势。", (
        "eafa54818ed54020a16369a42c99783f", "d093ae51d20942ffa69bfcea7a14f740"),
        "ServerPayLog 按业务小时统计真实交易事件次数和累计次数；金额问题转交收入 Skill。"),
    TopicDefinition("new-users-platform", "修仙新增用户总量与系统归因", "新增总量与系统归因。", (
        "1c5288d1fe144ddea2b9e82c5ac72b24", "bdc788729cbc4157bfe3046170c1f92a", "10d4c025e0bf4d9a9f3bd60194cdabb0"),
        "新增用户使用 UserRegister 去重 uid；系统归因读取注册事件行的 deviceinfo/userinfo，不能用后续活跃覆盖。"),
    TopicDefinition("channel-acquisition", "修仙渠道新增与投放获客", "渠道新增与单渠道获客。", (
        "8683537b4c2641afa1cefb2dec8dfb06", "b687a5175da64fc3a3d37ee9a0ec12b2", "918d4fd1c4d649d5bae371828928f409", "96d0dcd61c3a4a9e8a9922d813fce866", "d03e4b19ba1d4c668c9e6c64b5f16fc9"),
        "渠道归因取 UserRegister 注册行的 mediaSource/campaignName；新增用户按 uid 去重，不把活跃人数当新增。"),
    TopicDefinition("active-dau-wau-mau", "修仙 DAU、WAU 与 MAU", "活跃规模和周期去重。", (
        "6b458210dec64fdc8c067b301272f347", "e4344fa52c564002931ce13ea3657027", "0369399df2eb4a3299d6d34f9663101b", "ad88b71e2b08435c8c7a0606c5579f30"),
        "DAU/WAU/MAU 使用 UserActive 去重 uid；WAU/MAU 按完整自然周/月去重，不能相加日活。"),
    TopicDefinition("active-lifecycle", "修仙活跃生命周期与维度拆解", "活跃生命周期、渠道、系统和周登录天数。", (
        "fd9a8fe1127e4f21bf1809a6560ec6e2", "816451c6645a4451b7e85bbfb74d7ee7", "6c96d753e08742579580d52764d5589b", "d4675e033a9c4d4881264a66861b066e", "2ae501be08934d758f82802abf016059"),
        "活跃 cohort 使用 UserActive；生命周期、渠道、系统均取同一活跃事件上下文，周登录天数先按用户去重日期。"),
    TopicDefinition("new-user-retention", "修仙新增 cohort 留存", "新增 cohort D1/D3/D7 留存。", (
        "f99d0fb5f3624192953bdbfa31549abd", "531bc723e3cb42f0a1fe2c412d7f05b0", "57c366462db9418ba14fcde0febeb18d", "73f88ab0dce848f39037c345e20fe268", "b0f27793e48349c1a6a7fbf40ff03ffd", "e797a8af6785452e9fdcee7d80786b6e"),
        "分母固定 UserRegister cohort，Dn 分子为精确第 n 日 UserActive 去重 uid；排除未成熟 cohort。"),
    TopicDefinition("active-retention", "修仙活跃留存与回流", "活跃 cohort 留存。", (
        "464bc0c1f62049a5b2562fd09d699640",),
        "活跃留存先固定观察日 UserActive cohort，再按精确后续日期计算，不与新增留存混用。"),
    TopicDefinition("serverpaylog-revenue", "修仙 ServerPayLog 收入与 ARPU/ARPPU", "真实收入与付费人均指标。", (
        "22d89d4a69224e53994d21fb44b376aa", "2192510609759838208", "3b585529d8e84bc3ac1ea3bf55746450", "a6eb26710f7b4dc6ab69ded704c32fee", "9eff78876b1b405385f96d8559a286a8"),
        "收入只汇总 ServerPayLog.personal.money；ARPPU 分母为 ServerPayLog 去重 uid，ARPU 分母为 UserActive 去重 uid。"),
    TopicDefinition("payer-penetration", "修仙付费用户、渗透与累计付费", "付费用户、渗透率与累计金额。", (
        "95d8497afac14f0a90342031fb43bc04", "f499305aa9b44a209cbe72cb68985a46", "304e66bb74254b9e88d8711ce33d94cc", "e4b33de129da47629caa61612cca8100", "eba39b8352a34136872404c16fbd17a9", "fc272fe6a3a74cda90a0564a98890fab"),
        "日付费用户按 ServerPayLog.uid 去重；累计 paytotal 只用于明确的累计快照指标，不能替代当日收入。"),
    TopicDefinition("orders-products", "修仙订单、礼包、月卡与支付流程", "订单、商品、礼包、月卡留存和支付流程事件。", (
        "bcd7dc9ca6c349909fa74c8d4b0502d7", "ab85f87857774883833dbca9b5ea41ba", "e65001c16c52433e8afac84c6b2c92a0", "1e4e34743f2d47dfa1c2948742b93a50"),
        "真实订单和商品使用 ServerPayLog.personal.orderId/personal.productid；月卡购买 cohort 使用 ServerPayLog，留存活跃使用 UserActive；PayBuyRet 仅描述流程事件分布，不命名为真实交易。"),
    TopicDefinition("player-snapshot", "修仙当前等级、付费分层与用户快照", "当前等级和付费分层。", (
        "7f71477b49404ad289485f4f22d34c2f", "3a449b3049314a668661ae65f70e38f1"),
        "当前分布读取目标日期 user 快照；等级段人均累计付费使用 paytotal，并明确其累计快照语义。"),
    TopicDefinition("hero-growth", "修仙英雄养成", "英雄升级、升星和星级分布。", (
        "99e31069e8b54504a321b7b8066bf946", "7a582c5a24ab463a8378e43ae63eda83"),
        "英雄养成使用已确认的 HeroStarUp/HeroLevelUp 事件和 personal 英雄字段，按 uid 去重用户。"),
)
```

`build_topic_prompt` 将每个 guidance 放入“业务口径”段，并统一补充适用范围、日期规则引用、禁止事项、推荐输出和看板 SQL 段；收入主题必须明确 `ServerPayLog/personal.money`，订单主题必须区分 `ServerPayLog` 与仅作流程分析的 `PayBuyRet`。

- [ ] **Step 4: 实现目录校验并运行测试**

```python
def validate_catalog() -> None:
    mapped = [view_id for topic in TOPICS for view_id in topic.view_ids]
    if len(TOPICS) != 12 or len(mapped) != 45 or len(set(mapped)) != 45:
        raise ValueError("修仙推荐看板 Skill 目录数量或唯一性错误")
    if set(mapped) != EXPECTED_VIEW_IDS:
        raise ValueError("修仙推荐看板 Skill 目录存在遗漏或错误组件")
    if any(len(topic.view_ids) > MAX_SQL_BLOCKS_PER_SKILL for topic in TOPICS):
        raise ValueError("单个修仙 Data Skill 超过 SQL 块上限")
```

Run: `backend\.venv\Scripts\python.exe -m pytest tests/test_xiuxian_dashboard_skill_catalog.py -q`

Expected: PASS。

- [ ] **Step 5: 提交目录实现**

```powershell
git add tools/xiuxian_dashboard_skill_catalog.py tests/test_xiuxian_dashboard_skill_catalog.py
git commit -m "功能：建立修仙看板技能主题目录"
```

---

### Task 2: 实现不可绕过的 9/45/45 备份门禁

**Files:**
- Create: `tools/xiuxian_dashboard_snapshot.py`
- Test: `tests/test_xiuxian_dashboard_snapshot.py`

**Interfaces:**
- Produces: `DashboardSnapshot`、`DrawerSnapshot`、`load_recommended_dashboards(connection)`、`write_verified_backup(dashboards, backup_root, timestamp) -> Path`、`verify_backup(path) -> BackupManifest`。
- Consumes: Task 1 的租户、数据源和预期 view id 常量。

- [ ] **Step 1: 写失败测试，覆盖数量、哈希和不可覆盖**

```python
def test_write_verified_backup_contains_full_canvas_and_drawer_sql(tmp_path):
    dashboards = make_nine_dashboard_snapshots(drawer_count=45, nonempty_count=45)
    path = snapshot.write_verified_backup(dashboards, tmp_path, timestamp="20260716-120000")
    manifest = snapshot.verify_backup(path)
    assert manifest.dashboard_count == 9
    assert manifest.drawer_count == 45
    assert manifest.nonempty_drawer_count == 45
    assert len(list((path / "dashboards").glob("*.json"))) == 9


def test_backup_refuses_existing_directory(tmp_path):
    dashboards = make_nine_dashboard_snapshots(drawer_count=45, nonempty_count=45)
    snapshot.write_verified_backup(dashboards, tmp_path, timestamp="20260716-120000")
    with pytest.raises(FileExistsError):
        snapshot.write_verified_backup(dashboards, tmp_path, timestamp="20260716-120000")
```

- [ ] **Step 2: 运行测试并确认失败**

Run: `backend\.venv\Scripts\python.exe -m pytest tests/test_xiuxian_dashboard_snapshot.py -q`

Expected: FAIL，提示备份模块不存在。

- [ ] **Step 3: 实现系统库只读加载**

```python
RECOMMENDED_DASHBOARD_SQL = """
SELECT d.id, d.name, d.tenant_id, d.datasource, d.canvas_view_info
FROM core_dashboard d
JOIN core_dashboard_tree t
  ON t.dashboard_id = d.id AND t.tenant_id = d.tenant_id
WHERE d.tenant_id = %s
  AND d.datasource = %s
  AND t.scope = 'default'
  AND d.node_type = 'leaf'
  AND COALESCE(d.delete_flag, 0) = 0
ORDER BY t.sort, d.id
"""


def load_recommended_dashboards(connection) -> list[DashboardSnapshot]:
    with connection.cursor() as cur:
        cur.execute(RECOMMENDED_DASHBOARD_SQL, (TENANT_ID, DATASOURCE_ID))
        return [DashboardSnapshot.from_row(row) for row in cur.fetchall()]
```

`DashboardSnapshot.from_row` 必须解析但不重排原始 `canvas_view_info`，并为每个抽屉保存原 SQL和 `sha256(sql.encode("utf-8"))`。

- [ ] **Step 4: 实现原子备份和重新读取校验**

```python
def write_verified_backup(dashboards, backup_root: Path, timestamp: str) -> Path:
    target = backup_root / timestamp
    target.mkdir(parents=True, exist_ok=False)
    dashboards_dir = target / "dashboards"
    dashboards_dir.mkdir()
    for dashboard in dashboards:
        _write_json(dashboards_dir / f"{dashboard.id}.json", dashboard.to_backup_dict())
    _write_json(target / "drawer_sql.json", _drawer_rows(dashboards))
    _write_json(target / "manifest.json", _build_manifest(target, dashboards))
    verify_backup(target)
    return target
```

写入使用同级 staging 目录；`verify_backup` 重新读取全部 JSON，重新计算文件、SQL 和 manifest payload 哈希并严格检查 9/45/45，验签通过后再用 `Path.replace()` 原子发布最终目录，异常时清理 staging。

- [ ] **Step 5: 运行测试并提交**

Run: `backend\.venv\Scripts\python.exe -m pytest tests/test_xiuxian_dashboard_snapshot.py -q`

Expected: PASS。

```powershell
git add tools/xiuxian_dashboard_snapshot.py tests/test_xiuxian_dashboard_snapshot.py
git commit -m "功能：备份修仙推荐看板抽屉SQL"
```

- [ ] **Step 6: 在任何真实 SQL 夹具或改写工作前生成首份现场备份**

为 `xiuxian_dashboard_snapshot.py` 提供 `backup` 和 `verify <path>` CLI。使用系统库只读连接执行：

```powershell
backend\.venv\Scripts\python.exe tools\xiuxian_dashboard_snapshot.py backup
```

Expected: 输出 `.codex-runtime/xiuxian-dashboard-sql-backups/<timestamp>` 绝对路径，并报告 `dashboards=9 drawers=45 nonempty=45 verified=true`。立即执行 `verify <path>`，两次校验结果必须一致。Task 3 的测试夹具只能从该已验证备份的 `drawer_sql.json` 提取，不能重新读取 live SQL 后绕过备份。

---

### Task 3: 实现带 SHA 白名单的受限 bounds AST 改写

**Files:**
- Create: `tools/xiuxian_dashboard_sql_repair.py`
- Test: `tests/test_xiuxian_dashboard_sql_repair.py`

**Interfaces:**
- Produces: `RepairSpec`、`REPAIR_SPECS`、`rewrite_bounds_sql(view_id, sql) -> str`、`validate_rewritten_sql(sql)`。
- Consumes: Task 2 的 `DrawerSnapshot`。

- [ ] **Step 1: 写失败测试覆盖三种实际结构**

```python
def test_rewrite_removes_direct_bounds_join():
    rewritten = repair.rewrite_bounds_sql("95d8497afac14f0a90342031fb43bc04", SIMPLE_USER_SQL)
    assert "WITH bounds AS" not in rewritten
    assert "JOIN bounds" not in rewritten
    assert "u.dt BETWEEN" in rewritten


def test_rewrite_resolves_nested_calendar_cte():
    rewritten = repair.rewrite_bounds_sql("0369399df2eb4a3299d6d34f9663101b", WAU_SQL)
    assert "JOIN bounds" not in rewritten
    assert "e.dt BETWEEN" in rewritten
    assert "latest_week_start" not in _event_partition_predicate(rewritten)


def test_rewrite_preserves_bounds_value_used_by_downstream_join():
    rewritten = repair.rewrite_bounds_sql("fc272fe6a3a74cda90a0564a98890fab", CHANNEL_PAY_SQL)
    assert "b.max_dt" not in rewritten
    assert "latest.dt" in rewritten
```

测试夹具使用当前备份中的完整原 SQL，放在 `tests/fixtures/xiuxian_dashboard_sql_repairs.json`；夹具不得包含连接配置或业务结果数据。

- [ ] **Step 2: 运行测试确认失败**

Run: `backend\.venv\Scripts\python.exe -m pytest tests/test_xiuxian_dashboard_sql_repair.py -q`

Expected: FAIL，提示改写模块不存在。

- [ ] **Step 3: 写入当前 11 条 SQL 的 SHA-256 白名单**

```python
REPAIR_SOURCE_HASHES = {
    "95d8497afac14f0a90342031fb43bc04": "815c35585e7769575fa01ca6eb13069eaf47821da3943080b0968255b999b503",
    "f499305aa9b44a209cbe72cb68985a46": "364956182ef6e2dd84b5a30e66e99801741da627cec1797f7383ea9f8fa0e6b5",
    "f99d0fb5f3624192953bdbfa31549abd": "6385a9ac88f2908207a785d150565c1d8cf473bd1bbef0afd94381cea49cb261",
    "531bc723e3cb42f0a1fe2c412d7f05b0": "67ce7636a2a409cb4dcc9a9e773b74bc45b4fd63109b5ef71355dec73f13959e",
    "b0f27793e48349c1a6a7fbf40ff03ffd": "9d9ce46714e0472bbb43199efa90d8e51b29ac136d72a0f7652dfdb7219d2c58",
    "a6eb26710f7b4dc6ab69ded704c32fee": "4c2b7532ece58222c0e6e6e099394fd181389143cb14c280acebd70f4c875dd8",
    "0369399df2eb4a3299d6d34f9663101b": "75df3dbb120f0da0423e12116a6f3513540edec98ccef3d7a2fab32a392fdf11",
    "ad88b71e2b08435c8c7a0606c5579f30": "148640112c5a584360fd643f5a8a331d7041b6a95ee1d092ff0a308acf146cd2",
    "d4675e033a9c4d4881264a66861b066e": "afdbcc182590860c6fb89aafb14f8ce1994c654829af21f7e8b34f89b0c04e4c",
    "e797a8af6785452e9fdcee7d80786b6e": "6385a9ac88f2908207a785d150565c1d8cf473bd1bbef0afd94381cea49cb261",
    "fc272fe6a3a74cda90a0564a98890fab": "27ebb37991f8177f460650ac359a8aedbd4dc06033ca5a8cb7293c71b2a7a9fe",
}
```

入口先验证 SHA；不匹配时抛出 `SourceSqlChangedError`，不得尝试改写。

- [ ] **Step 4: 实现受限 scalar CTE 解析和替换**

使用 `sqlglot.parse_one(sql, read="mysql")`，只解析 `bounds` 及其单行依赖 `weeks`、`months`。解析器必须：

1. 将 scalar CTE SELECT 别名解析为表达式映射。
2. 递归展开 `bounds` 对 `weeks/months` 输出列的引用。
3. 在引用 `bounds` 的 SELECT 内替换 `b.start_dt/end_dt/max_dt/data_end_dt`。
4. 删除 `JOIN bounds b ON <date-predicate>`，把替换后的 date predicate 与原 WHERE 用 `AND` 合并。
5. 删除不再被引用的 scalar CTE，保留 cohort、active、daily 等业务 CTE。
6. 用 MySQL 方言重新生成 SQL，并调用 `validate_rewritten_sql`。

```python
def rewrite_bounds_sql(view_id: str, sql: str) -> str:
    _require_source_hash(view_id, sql)
    tree = sqlglot.parse_one(sql, read="mysql")
    scalar_values = _resolve_scalar_cte_values(tree, allowed={"bounds", "weeks", "months"})
    _inline_scalar_joins(tree, scalar_values)
    _drop_unreferenced_scalar_ctes(tree, scalar_values)
    rewritten = tree.sql(dialect="mysql", pretty=True)
    validate_rewritten_sql(rewritten)
    return rewritten
```

- [ ] **Step 5: 加入防扩散校验**

`validate_rewritten_sql` 必须拒绝：仍引用 `bounds`、出现 `MAX(dt)`、任意 `event/user` TableScan 所在 SELECT 没有该别名 `dt` 条件、输出字段/Group/Order/Limit 表面签名与原 SQL不同。

- [ ] **Step 6: 运行测试和现有日期规则回归测试**

Run: `backend\.venv\Scripts\python.exe -m pytest tests/test_xiuxian_dashboard_sql_repair.py backend/tests/test_xiuxian_data_skill_seed.py::test_xiuxian_date_skill_rejects_bounds_cte_join_for_partition_filter -q`

Expected: PASS。

- [ ] **Step 7: 提交改写器**

```powershell
git add tools/xiuxian_dashboard_sql_repair.py tests/test_xiuxian_dashboard_sql_repair.py tests/fixtures/xiuxian_dashboard_sql_repairs.json
git commit -m "功能：改写修仙看板日期边界SQL"
```

---

### Task 4: 实现冻结日期、结果等价、EXPLAIN 和事务更新

**Files:**
- Modify: `tools/xiuxian_dashboard_sql_repair.py`
- Modify: `tests/test_xiuxian_dashboard_sql_repair.py`

**Interfaces:**
- Produces: `freeze_curdate(sql, business_date)`、`execute_query`、`compare_query_results`、`validate_explain_plan`、`apply_dashboard_repairs`。
- Consumes: Task 3 的 `rewrite_bounds_sql`。

- [ ] **Step 1: 写结果比较失败测试**

```python
def test_compare_results_reports_first_cell_difference():
    original = QueryResult(("日期", "DAU"), [(date(2026, 7, 15), Decimal("10"))])
    rewritten = QueryResult(("日期", "DAU"), [(date(2026, 7, 15), Decimal("11"))])
    with pytest.raises(ResultMismatchError, match="DAU"):
        compare_query_results(original, rewritten, ordered=True)


def test_unordered_compare_preserves_duplicate_rows():
    left = QueryResult(("x",), [(1,), (1,), (2,)])
    right = QueryResult(("x",), [(1,), (2,), (2,)])
    with pytest.raises(ResultMismatchError):
        compare_query_results(left, right, ordered=False)
```

- [ ] **Step 2: 写冻结 `CURDATE()` 测试**

```python
def test_freeze_curdate_uses_one_database_date_for_both_queries():
    frozen = freeze_curdate("SELECT DATE_SUB(CURDATE(), INTERVAL 1 DAY)", date(2026, 7, 16))
    assert "CURDATE" not in frozen.upper()
    assert "DATE '2026-07-16'" in frozen or "'2026-07-16'" in frozen
```

- [ ] **Step 3: 运行测试确认失败**

Run: `backend\.venv\Scripts\python.exe -m pytest tests/test_xiuxian_dashboard_sql_repair.py -q`

Expected: FAIL，提示比较和日期冻结函数不存在。

- [ ] **Step 4: 实现类型规范化和严格比较**

```python
def normalize_cell(value):
    if value is None:
        return ("null", None)
    if isinstance(value, Decimal):
        return ("decimal", value.normalize().to_eng_string())
    if isinstance(value, (date, datetime)):
        return ("date", value.isoformat())
    if isinstance(value, float):
        return ("float", Decimal(str(value)).normalize().to_eng_string())
    return (type(value).__name__, value)
```

有 `ORDER BY` 时逐行比较；否则对规范化完整行使用 `Counter`，保留重复行计数。不得添加业务数值容差。

- [ ] **Step 5: 实现只读执行与 EXPLAIN 门禁**

在一个 PyMySQL 会话先执行 `SELECT CURDATE()`，对同一 view 的原/新 SQL都调用 `freeze_curdate` 后执行。连接使用 `connect_timeout=10`、`read_timeout=120`、`write_timeout=120`；日志不得输出连接配置。

```python
def validate_explain_plan(plan: str) -> None:
    if "Exchange[REPLICATE]" in plan and "-> Values" in plan and "InnerJoin[Hash Join]" in plan:
        raise UnsafePlanError("日期边界仍生成广播 Hash Join")
```

- [ ] **Step 6: 写 CAS 事务测试并实现系统库更新**

```python
UPDATE core_dashboard
SET canvas_view_info = %s,
    update_time = %s
WHERE id = %s
  AND tenant_id = %s
  AND canvas_view_info = %s
```

在同一事务内更新 6 个受影响看板；每行 `rowcount` 必须为 1，否则 rollback。只替换目标 view 的 `sql`，保留原 data、chart、fields、pivot 和快照字段。

- [ ] **Step 7: 运行测试并提交**

Run: `backend\.venv\Scripts\python.exe -m pytest tests/test_xiuxian_dashboard_sql_repair.py -q`

Expected: PASS。

```powershell
git add tools/xiuxian_dashboard_sql_repair.py tests/test_xiuxian_dashboard_sql_repair.py
git commit -m "功能：验证并事务更新修仙看板SQL"
```

---

### Task 5: 将修仙种子扩展为 13 条主题 Skill 并迁移 ServerPayLog 口径

**Files:**
- Modify: `tools/seed_xiuxian_data_skills.py`
- Modify: `tests/test_seed_xiuxian_data_skills.py`
- Modify: `backend/tests/test_xiuxian_data_skill_seed.py`

**Interfaces:**
- Produces: `build_data_skills(dashboards) -> list[dict[str, str]]`、`upsert_skills`、`backup_existing_skills`、`restore_skills`、`verify_embeddings`。
- Consumes: Task 1 的 `TOPICS` 和 Task 2 的看板快照。

- [ ] **Step 1: 将旧 PayBuyRet 测试改成 ServerPayLog 失败测试**

```python
def test_xiuxian_payment_skill_uses_serverpaylog_authority():
    prompt = _payment_skill()["prompt"]
    assert "event = 'ServerPayLog'" in prompt
    assert "personal.money" in prompt
    assert "personal.orderId" in prompt
    assert "COUNT(DISTINCT uid)" in prompt
    assert "PayBuyRet" not in _revenue_rule_section(prompt)


def test_serverpaylog_arppu_validation_rejects_paybuyret_revenue_sql():
    error = _data_skill_sql_validation_error("查看近七天 ARPPU", PAYBUYRET_ARPPU_SQL, _payment_skill()["prompt"])
    assert "ServerPayLog" in error
```

- [ ] **Step 2: 写 13 条 Skill 和 Prompt 体积失败测试**

```python
def test_build_data_skills_produces_one_base_and_twelve_topics(dashboard_snapshots):
    skills = seed.build_data_skills(dashboard_snapshots)
    assert len(skills) == 13
    assert sum(prompt.count("<!-- dashboard-sql:") for prompt in [s["prompt"] for s in skills]) == 45
    assert all(len(s["prompt"]) <= 15_000 for s in skills)
```

- [ ] **Step 3: 运行目标测试确认失败**

Run: `backend\.venv\Scripts\python.exe -m pytest tests/test_seed_xiuxian_data_skills.py backend/tests/test_xiuxian_data_skill_seed.py -q`

Expected: FAIL，旧 Prompt 仍要求 PayBuyRet 且 Skill 数为 2。

- [ ] **Step 4: 实现 Prompt 构建和 SQL 块注入**

```python
def dashboard_sql_block(view_id: str, sql: str) -> str:
    return f"<!-- dashboard-sql:{view_id} -->\n```sql\n{sql.strip()}\n```"


def build_data_skills(dashboards) -> list[dict[str, str]]:
    by_view_id = index_nonempty_drawers(dashboards)
    validate_catalog()
    skills = [DATE_PARTITION_SKILL]
    for topic in TOPICS:
        blocks = [dashboard_sql_block(view_id, by_view_id[view_id].sql) for view_id in topic.view_ids]
        prompt = build_topic_prompt(topic, blocks)
        if len(blocks) > 6 or len(prompt) > 15_000:
            raise ValueError(f"Skill 体积超限: {topic.slug}")
        skills.append({"name": topic.name, "description": topic.description, "prompt": prompt})
    return skills
```

ServerPayLog 收入 Skill 使用 marker `data-skill-source:xiuxian:serverpaylog-monetization-arppu`；SQL 校验要求 `ServerPayLog`、`$.money`、`COUNT(DISTINCT uid)`，并禁止收入类问题使用 `PayBuyRet`、`ed_money` 或快照 `paytotal` 作为当日收入。

- [ ] **Step 5: 实现 legacy marker 定位和同 id 迁移**

upsert 查询先找当前 marker；ServerPayLog Skill 未找到时，再在相同 tenant/datasource 作用域内找旧 marker `data-skill-source:xiuxian:paybuyret-monetization-arppu`。更新时写入新 Prompt，新 Prompt 不得保留旧 marker。

- [ ] **Step 6: 实现 Skill 快照、恢复和 embedding 签名验证**

Skill 备份保存受影响 `custom_prompt` 完整列以及 `custom_prompt_user_preference`。`verify_embeddings` 解析 embedding 维度并调用 `skill_definition_signature(name, description, prompt, model, dim)` 比较签名。

- [ ] **Step 7: 运行测试并提交**

Run: `backend\.venv\Scripts\python.exe -m pytest tests/test_seed_xiuxian_data_skills.py backend/tests/test_xiuxian_data_skill_seed.py -q`

Expected: PASS。

```powershell
git add tools/seed_xiuxian_data_skills.py tests/test_seed_xiuxian_data_skills.py backend/tests/test_xiuxian_data_skill_seed.py
git commit -m "功能：生成修仙看板主题技能"
```

---

### Task 6: 编排 dry-run、apply、恢复和召回冒烟测试

**Files:**
- Create: `tools/publish_xiuxian_dashboard_data_skills.py`
- Test: `tests/test_publish_xiuxian_dashboard_data_skills.py`

**Interfaces:**
- Produces: `run_publish(mode, backup_root, system_connection_factory, datasource_connection_factory) -> PublishReport` 和 CLI `--mode dry-run|apply`。
- Consumes: Tasks 2-5 的备份、改写、验证、Skill 发布接口。

- [ ] **Step 1: 写编排顺序失败测试**

```python
def test_dry_run_backs_up_and_validates_without_writes(fakes):
    report = publisher.run_publish(mode="dry-run", **fakes)
    assert fakes.calls[:3] == ["load", "backup", "verify_backup"]
    assert "apply_dashboards" not in fakes.calls
    assert "upsert_skills" not in fakes.calls
    assert report.repaired_view_count == 11


def test_apply_stops_before_writes_when_one_result_differs(fakes):
    fakes.compare_error = ResultMismatchError(
        "view=95d8497afac14f0a90342031fb43bc04 field=累计付费率"
    )
    with pytest.raises(ResultMismatchError):
        publisher.run_publish(mode="apply", **fakes)
    assert "apply_dashboards" not in fakes.calls
```

- [ ] **Step 2: 运行测试确认失败**

Run: `backend\.venv\Scripts\python.exe -m pytest tests/test_publish_xiuxian_dashboard_data_skills.py -q`

Expected: FAIL，发布模块不存在。

- [ ] **Step 3: 实现不可绕过的状态机**

```python
class PublishPhase(Enum):
    LOADED = auto()
    BACKED_UP = auto()
    BACKUP_VERIFIED = auto()
    SQL_EQUIVALENT = auto()
    PLANS_VERIFIED = auto()
    DASHBOARDS_APPLIED = auto()
    SKILLS_APPLIED = auto()
    EMBEDDINGS_VERIFIED = auto()


def run_publish(
    mode: str,
    backup_root: Path,
    system_connection_factory: Callable[[], Any],
    datasource_connection_factory: Callable[[], Any],
    embedding_refresher: Callable[[list[int]], int],
    retrieval_checker: Callable[[str], str],
) -> PublishReport:
    dashboards = load_recommended_dashboards(system_connection_factory())
    backup_path = write_verified_backup(dashboards, backup_root, utc_timestamp())
    verify_backup(backup_path)
    datasource_connection = datasource_connection_factory()
    repairs = validate_all_repairs(dashboards, datasource_connection)
    validate_all_plans(repairs, datasource_connection)
    skills = build_data_skills(apply_repairs_in_memory(dashboards, repairs))
    if mode == "dry-run":
        return PublishReport.dry_run(backup_path, repairs, skills)
    system_connection = system_connection_factory()
    apply_dashboard_repairs(system_connection, dashboards, repairs)
    backup_existing_skills(system_connection, backup_path)
    try:
        ids = upsert_skills(system_connection, skills)
        refresh_and_verify_embeddings(system_connection, ids, embedding_refresher)
        verify_retrieval(retrieval_checker)
    except Exception:
        restore_skills(system_connection_factory(), backup_path)
        raise
    return PublishReport.applied(backup_path, repairs, ids)
```

`mode` 默认 `dry-run`；只有显式 `--mode apply` 可写系统库。脚本不得接受 tenant 或 datasource 覆盖参数。

- [ ] **Step 4: 加入 Skill 召回冒烟验证**

apply 后使用 `find_data_skills(session, datasource=6, tenant_id=7482727237662281728, target_scope='SMART_QA', question=question)` 依次验证五个问题：`最近七天新增用户趋势`、`最近一个月 DAU WAU MAU`、`各渠道新增用户次日留存`、`最近七天收入和 ARPPU`、`英雄升级与升星情况`。返回文本必须包含对应主题 Skill 名；ARPPU 返回文本必须含 `ServerPayLog`，不得含旧 `paybuyret-monetization-arppu` marker。

- [ ] **Step 5: 运行测试并提交**

Run: `backend\.venv\Scripts\python.exe -m pytest tests/test_publish_xiuxian_dashboard_data_skills.py -q`

Expected: PASS。

```powershell
git add tools/publish_xiuxian_dashboard_data_skills.py tests/test_publish_xiuxian_dashboard_data_skills.py
git commit -m "功能：编排修仙看板技能安全发布"
```

---

### Task 7: 执行完整本地回归和计划约束检查

**Files:**
- Modify only if tests expose a defect in Tasks 1-6.

**Interfaces:**
- Consumes: Tasks 1-6 的全部实现。
- Produces: 可进入 live dry-run 的已验证提交。

- [ ] **Step 1: 运行修仙专项测试**

Run:

```powershell
backend\.venv\Scripts\python.exe -m pytest tests/test_xiuxian_dashboard_skill_catalog.py tests/test_xiuxian_dashboard_snapshot.py tests/test_xiuxian_dashboard_sql_repair.py tests/test_publish_xiuxian_dashboard_data_skills.py tests/test_seed_xiuxian_data_skills.py backend/tests/test_xiuxian_data_skill_seed.py -q
```

Expected: 全部 PASS，0 failed。

- [ ] **Step 2: 运行共享 SQL 解析和 Data Skill 回归测试**

Run:

```powershell
backend\.venv\Scripts\python.exe -m pytest backend/tests/test_llm_sql_answer_parser.py backend/tests/test_dashboard_ai_sql_generator.py tests/test_custom_prompt_agent_permissions.py backend/tests/test_custom_prompt_datasource_scope.py -q
```

Expected: 全部 PASS，0 failed。

- [ ] **Step 3: 运行静态约束检查**

Run:

```powershell
rg -n "paybuyret-monetization-arppu|required_sql_contains.*PayBuyRet|ed_money" tools/seed_xiuxian_data_skills.py tools/xiuxian_dashboard_skill_catalog.py
git diff --check
```

Expected: 第一个命令只命中 legacy lookup 常量或明确的“流程事件非收入”说明；`git diff --check` 无输出。

- [ ] **Step 4: 提交回归修正（仅在有修正时）**

```powershell
git add tools tests backend/tests
git commit -m "测试：完善修仙看板技能发布回归"
```

---

### Task 8: 现场 dry-run、备份审计、apply 和 embedding 验证

**Files:**
- Runtime only: `.codex-runtime/xiuxian-dashboard-sql-backups/<timestamp>/`
- No committed file changes expected.

**Interfaces:**
- Consumes: Task 7 已验证提交、系统库和 datasource 6 只读连接、远程 embedding 服务。
- Produces: 11 个已修复看板 SQL、13 条有效修仙 Skill、完整 embedding 和现场证据。

- [ ] **Step 1: 在同一 PowerShell 进程加载本地后端运行环境**

按仓库 `AGENTS.md` Local Dev Runbook 设置系统库、Redis、`SECRET_KEY`、embedding endpoint/model 环境变量；不得把值打印到终端或写入新文件。

- [ ] **Step 2: 执行 dry-run**

Run:

```powershell
backend\.venv\Scripts\python.exe tools\publish_xiuxian_dashboard_data_skills.py --mode dry-run
```

Expected report:

- backup verified: dashboards=9, drawers=45, nonempty=45
- repair candidates=11
- equivalent results=11
- safe explain plans=11
- generated skills=13
- no system database writes

- [ ] **Step 3: 独立审计备份**

重新运行工具提供的 `verify_backup` CLI 子命令，并人工抽查 `manifest.json`、`drawer_sql.json` 和至少一个完整 dashboard JSON。确认备份路径位于 `.codex-runtime`、45 条 SQL 均有 SHA-256、目标 11 条 source hash 与 Task 3 白名单一致。

- [ ] **Step 4: 执行 apply**

Run:

```powershell
backend\.venv\Scripts\python.exe tools\publish_xiuxian_dashboard_data_skills.py --mode apply
```

Expected report:

- dashboards updated=6
- views updated=11
- skills upserted=13
- embeddings saved=13
- embeddings verified=13
- recall smoke tests=5/5

- [ ] **Step 5: 现场数据库复核**

只读查询系统库，确认：

- 11 个目标 view SQL SHA 与 dry-run 生成的 rewritten SHA 一致。
- 目标 SQL不含 `JOIN bounds`、`CROSS JOIN bounds`、`FROM bounds` 或 `MAX(dt)`。
- datasource 6 恰有本目录定义的 13 条 active/visible Data Skill。
- 每条 Skill 的 `specific_ds=true`、`datasource_ids=[6]`、embedding 非空、签名匹配。
- 旧 `paybuyret-monetization-arppu` marker 不在任何已发布 Prompt 中。

- [ ] **Step 6: 最终 Git 与运行产物检查**

Run:

```powershell
git status --short
git log -8 --oneline
```

Expected: 只有用户原有未提交修改；`.codex-runtime` 备份不出现在 Git 状态中。记录最终分支提交、备份绝对路径、11 条等价验证摘要、13 个 Skill id 和 embedding 验证数量。
