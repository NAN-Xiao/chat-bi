# Platform Realtime Event Table Skill Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 新增并发布一条平台公开 Data Skill，使未完成当日问题条件式选择 `event_realtime`，完整历史问题选择 `event`。

**Architecture:** 使用独立、幂等的发布脚本维护唯一 `PLATFORM_PUBLIC` 记录，不修改全局 Agent prompt、通用 SQL 生成规则或 datasource-scoped Skill。Skill 通过结构化 `data-skill-requires-tables` 声明 Schema 前置条件，检索层在排序前复用 `build_permission_scope` 按当前用户有效授权表集合确定性过滤。脚本通过 backend protocol 分离纯规则、发布状态机和 PostgreSQL/embedding 适配器，以便用内存 fake 完成失败恢复测试，再执行真实 dry-run/apply 与检索验收。

**Tech Stack:** Python 3.11、pytest、psycopg 3、SQLAlchemy、自有 `custom_prompt` Data Skill 与 embedding 服务。

## Global Constraints

- 仅当当前授权数据源同时存在 `event` 和 `event_realtime` 时生效。
- 平台 Skill 只决定选表，不定义业务事件名、产品 ID、主体键或金额字段。
- 实时表不存在、无权限或字段不满足时不得静默回退到 `event`。
- 目标记录固定为 `tenant_id=1`、`visibility_scope=PLATFORM_PUBLIC`、`specific_ds=false`、`datasource_ids=[]`。
- 目标 Skill 固定声明 `data-skill-requires-tables=["event","event_realtime"]`，缺少任一表时不得注入模型上下文。
- 默认 dry-run；只有显式 `--apply` 才允许写库。
- 只提交本任务文件，保留工作区其他未提交内容。

---

### Task 1: Data Skill 内容与发布状态机契约

**Files:**
- Create: `tests/test_seed_platform_realtime_event_table_skill.py`
- Create: `tools/seed_platform_realtime_event_table_skill.py`

**Interfaces:**
- Produces: `SKILL: dict[str, str]`、`PublishReport`、`publish_skill(backend: PublishBackend, apply: bool) -> PublishReport`。
- Consumes: 当前平台 Data Skill 表结构与 embedding 刷新能力。

- [ ] **Step 1: 写入失败的内容契约测试**

```python
def test_skill_is_platform_public_and_keeps_business_semantics_out():
    assert module.PLATFORM_TENANT_ID == 1
    assert module.VISIBILITY_SCOPE == "PLATFORM_PUBLIC"
    assert module.SPECIFIC_DS is False
    prompt = module.SKILL["prompt"]
    for token in ("event_realtime", "event", "今天", "当天", "截至目前", "按小时"):
        assert token in prompt
    for business_token in ("UserRegister", "ServerPayLog", "110000047", "$.money"):
        assert business_token not in prompt

def test_skill_forbids_silent_fallback_and_requires_current_schema():
    prompt = module.SKILL["prompt"]
    assert "同时存在" in prompt
    assert "不得静默" in prompt
    assert "权限" in prompt
    assert "工作空间" in prompt
```

- [ ] **Step 2: 运行内容测试并确认因模块缺失而失败**

Run: `backend\.venv\Scripts\python.exe -m pytest tests/test_seed_platform_realtime_event_table_skill.py -q`

Expected: FAIL，提示无法导入 `seed_platform_realtime_event_table_skill`。

- [ ] **Step 3: 写入失败的状态机测试**

```python
def test_dry_run_never_writes_or_refreshes_embedding():
    backend = FakeBackend()
    report = module.publish_skill(backend, apply=False)
    assert report.updated is False
    assert backend.events == ["inspect"]

def test_apply_updates_only_target_and_verifies_embedding():
    backend = FakeBackend()
    report = module.publish_skill(backend, apply=True)
    assert report.updated is True
    assert report.embedding_verified is True
    assert backend.updated_markers == [module.SKILL_MARKER]

def test_embedding_failure_restores_only_target():
    backend = FakeBackend(embedding_error=RuntimeError("embedding failed"))
    with pytest.raises(RuntimeError, match="embedding failed"):
        module.publish_skill(backend, apply=True)
    assert backend.restored_markers == [module.SKILL_MARKER]
```

- [ ] **Step 4: 实现最小 Skill 与发布状态机**

```python
SKILL_MARKER = "<!-- data-skill-source:platform:realtime-event-table-selection -->"
PLATFORM_TENANT_ID = 1
VISIBILITY_SCOPE = "PLATFORM_PUBLIC"
SPECIFIC_DS = False

@dataclass(frozen=True)
class PublishReport:
    mode: str
    skill_id: int | None
    updated: bool
    embedding_verified: bool

def publish_skill(backend: PublishBackend, *, apply: bool) -> PublishReport:
    snapshot = backend.inspect(SKILL_MARKER)
    if not apply:
        return PublishReport("dry-run", snapshot.skill_id, False, False)
    backup = backend.backup(snapshot)
    expected_state = None
    try:
        backend.acquire_lock()
        expected_state = backend.upsert(SKILL, snapshot)
        backend.refresh_embedding(expected_state.skill_id)
        backend.verify(SKILL, expected_state)
        return PublishReport("apply", expected_state.skill_id, True, True)
    except BaseException:
        if expected_state is not None:
            backend.restore(backup, expected_state)
        raise
    finally:
        backend.release_lock()
```

- [ ] **Step 5: 运行测试确认绿色**

Run: `backend\.venv\Scripts\python.exe -m pytest tests/test_seed_platform_realtime_event_table_skill.py -q`

Expected: PASS，所有内容契约与状态机测试通过。

### Task 2: PostgreSQL 幂等发布、CAS 与恢复

**Files:**
- Modify: `tools/seed_platform_realtime_event_table_skill.py`
- Modify: `tests/test_seed_platform_realtime_event_table_skill.py`

**Interfaces:**
- Consumes: `core_system_db.core_system_db_config()`、`apps.chat.curd.custom_prompt_embedding.save_custom_prompt_skill_embedding()`。
- Produces: `PsycopgPublishBackend`、CLI `main(argv: Sequence[str] | None = None) -> int`。

- [ ] **Step 1: 添加数据库适配器失败测试**

```python
def test_duplicate_marker_is_rejected_before_write():
    backend = FakeBackend(marker_count=2)
    with pytest.raises(RuntimeError, match="marker"):
        module.publish_skill(backend, apply=True)
    assert "upsert" not in backend.events

def test_cli_defaults_to_dry_run(monkeypatch, capsys):
    backend = FakeBackend()
    monkeypatch.setattr(module, "PsycopgPublishBackend", lambda: backend)
    assert module.main([]) == 0
    assert "dry-run" in capsys.readouterr().out
    assert "upsert" not in backend.events
```

- [ ] **Step 2: 运行新增测试确认按预期失败**

Run: `backend\.venv\Scripts\python.exe -m pytest tests/test_seed_platform_realtime_event_table_skill.py -q`

Expected: FAIL，缺少 `PsycopgPublishBackend` 或 CLI 行为。

- [ ] **Step 3: 实现数据库适配器**

实现以下约束：

```python
SELECT id, name, description, prompt, tenant_id, type, active, visible,
       visibility_scope, specific_ds, datasource_ids, embedding, embedding_signature
FROM custom_prompt
WHERE type = 'DATA_SKILL'
  AND visibility_scope = 'PLATFORM_PUBLIC'
  AND position(%s in COALESCE(prompt, '')) > 0
ORDER BY id
```

- marker 结果超过一条时拒绝发布。
- `pg_advisory_lock(hashtext(marker))` 串行化发布。
- 更新使用原始 prompt/目标缺失状态作为 CAS 条件；插入固定平台作用域。
- 写入前将目标快照保存到 `.codex-runtime/platform-data-skill-backups/<timestamp>/skill.json`。
- 更新时清空 embedding 与 signature，提交后调用平台 tenant `1` 的 embedding 刷新。
- 回读验证 name、description、prompt、作用域、非空 embedding/signature。
- 失败恢复只按 marker 和目标 ID 还原本记录；新插入记录则删除该目标记录。

- [ ] **Step 4: 实现 CLI**

```python
parser.add_argument("--mode", choices=("dry-run", "apply"), default="dry-run")
report = publish_skill(PsycopgPublishBackend(), apply=args.mode == "apply")
print(json.dumps(asdict(report), ensure_ascii=False))
```

- [ ] **Step 5: 运行目标测试和静态检查**

Run: `backend\.venv\Scripts\python.exe -m pytest tests/test_seed_platform_realtime_event_table_skill.py -q`

Run: `backend\.venv\Scripts\python.exe -m py_compile tools/seed_platform_realtime_event_table_skill.py`

Expected: 两条命令均退出码 `0`。

### Task 3: 真实发布与检索验收

**Files:**
- Modify only through runtime data: system database `custom_prompt`
- Runtime backup: `.codex-runtime/platform-data-skill-backups/`（不得提交）

**Interfaces:**
- Consumes: Task 2 CLI、当前系统数据库、远程 `text-embedding-v4`。
- Produces: 一条可回读且可召回的平台公开 Data Skill。

在发布前先扩展 `backend/apps/chat/curd/custom_prompt.py` 的通用 Data Skill 前置表过滤，并在 `backend/tests/test_custom_prompt_datasource_scope.py` 覆盖双表存在/缺失两条路径；该过滤必须在自动排序和 prompt 拼装之前完成。

- [ ] **Step 1: 执行只读预检**

Run: `backend\.venv\Scripts\python.exe tools/seed_platform_realtime_event_table_skill.py --mode dry-run`

Expected: JSON 报告 `mode=dry-run`、`updated=false`，数据库无修改。

- [ ] **Step 2: 显式发布**

Run: `backend\.venv\Scripts\python.exe tools/seed_platform_realtime_event_table_skill.py --mode apply`

Expected: JSON 报告 `updated=true`、`embedding_verified=true`，并输出目标 Skill ID 与备份路径。

- [ ] **Step 3: 数据库回读作用域与 embedding**

通过 SQLAlchemy 使用系统配置查询唯一 marker，断言：

```python
assert row["tenant_id"] == 1
assert row["visibility_scope"] == "PLATFORM_PUBLIC"
assert row["specific_ds"] is False
assert row["datasource_ids"] == []
assert row["embedding"]
assert row["embedding_signature"]
```

- [ ] **Step 4: 验证两条目标问题的 Data Skill 检索**

使用 `find_data_skills` 的真实 session、datasource `6` 和修仙 tenant，分别检索：

```text
按小时统计今天的新增用户数量
给我生成当天的实时信息,包括实时收入
```

Expected: 两次返回的 Skill 列表均包含目标平台 Skill，prompt 中包含 `event_realtime`。

- [ ] **Step 5: 验证负面边界**

检索“不含实时表的数据源昨天收入趋势”，确认 Skill prompt 本身要求实时 Schema 双表条件，并且没有任何自动回退 SQL 或业务字段硬编码。

- [ ] **Step 6: 运行最终回归与差异检查**

Run: `backend\.venv\Scripts\python.exe -m pytest tests/test_seed_platform_realtime_event_table_skill.py backend/tests/test_custom_prompt_datasource_scope.py -q`

Run: `git diff --check`

Expected: 测试全部通过；本任务文件无 whitespace error。检查 `git status --short`，不得暂存或提交日志及用户已有修改。

- [ ] **Step 7: 提交实现**

```powershell
git add -- tools/seed_platform_realtime_event_table_skill.py tests/test_seed_platform_realtime_event_table_skill.py docs/superpowers/plans/2026-07-23-platform-realtime-event-table-skill.md
git diff --cached --check
git commit -m "功能：新增平台通用实时事件选表 Skill"
```
