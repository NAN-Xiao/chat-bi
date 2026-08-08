# AI 看板日期契约修复实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 消除 flam 与修仙 AI 看板中 `missing_parameters`、`database_current_date`、`metric_chart` 三类日期契约失败，并通过真实 UI 证明修复生效。

**Architecture:** 保留后端日期校验为唯一强制边界，将日期契约错误接入现有有限 SQL 重试图，使模型按明确错误码重新生成完整 JSON，而不是由后端猜字段。同步清理两个数据源的工作空间 Data Skill 中与看板 token 冲突的可变日期示例，幂等发布并回读验证。

**Tech Stack:** Python 3.11、FastAPI/SQLModel、LangGraph、pytest、PostgreSQL、Playwright/真实 Vite UI。

## Global Constraints

- 固定语义 `metric` 卡不生成 `date_filter`。
- 可变时间图表的 SQL 必须保留与 `date_parameter_type` 匹配的看板日期 token。
- 配置 `date_filter` 的 SQL 不得使用数据库当前日期函数。
- 不增加字段猜测、静默删除配置或跨数据源业务硬编码。
- 只发布 tenant/datasource 精确匹配的 flam `3` 与修仙 `6` 工作空间 Data Skill。

---

### Task 1: 将日期契约错误接入有限 SQL 重试

**Files:**
- Modify: `backend/apps/chat/task/sql_repair.py`
- Modify: `backend/apps/chat/task/smart_qa_graph.py`
- Test: `backend/tests/test_sql_repair.py`
- Test: `backend/tests/test_smart_qa_graph.py`

**Interfaces:**
- Consumes: `ChatDateFilterConfigurationError(reason: str)`、`SqlRepairContext`、现有 `repair_sql -> prepare_sql` 环路。
- Produces: `SqlRepairReason.DATE_FILTER_CONFIGURATION`，最多沿用 `SQL_REPAIR_MAX_ATTEMPTS=2` 次重试。

- [x] **Step 1: 写错误分类与修复消息失败测试**

```python
def test_prepare_error_classifies_dashboard_date_contract() -> None:
    error = ChatDateFilterConfigurationError("missing_parameters")
    assert classify_prepare_sql_error(error) == SqlRepairReason.DATE_FILTER_CONFIGURATION


def test_dashboard_date_contract_repair_message_requires_consistent_json() -> None:
    context = SqlRepairContext(
        reason=SqlRepairReason.DATE_FILTER_CONFIGURATION,
        dialect="mysql",
        failed_sql='{"chart-type":"line","date_filter":{}}',
        error_message="missing_parameters",
        violation=None,
        attempt=0,
    )
    message = build_sql_repair_message(context)
    assert "固定语义 metric" in message
    assert "看板日期 token" in message
    assert "不得使用 CURDATE" in message
```

- [x] **Step 2: 运行测试并确认因缺少新枚举/分类而失败**

Run: `cd backend; ./.venv/Scripts/python.exe -m pytest tests/test_sql_repair.py -k "dashboard_date_contract" -q`

Expected: FAIL，错误指向 `DATE_FILTER_CONFIGURATION` 不存在或错误未被分类。

- [x] **Step 3: 最小实现类型分类与专用修复指令**

```python
class SqlRepairReason(str, Enum):
    DATE_FILTER_CONFIGURATION = "date_filter_configuration"


def classify_prepare_sql_error(error: Exception) -> SqlRepairReason | None:
    if any(isinstance(item, ChatDateFilterConfigurationError) for item in _walk_error_chain(error)):
        return SqlRepairReason.DATE_FILTER_CONFIGURATION
    # 保留现有分支


def build_sql_repair_message(context: SqlRepairContext) -> str:
    payload = {
        "reason": context.reason.value,
        "dialect": context.dialect,
        "failed_sql": context.failed_sql,
        "error": sanitize_sql_repair_error(context.error_message),
        "attempt": context.attempt,
        "max_attempts": context.max_attempts,
        "violation": asdict(context.violation) if context.violation is not None else None,
    }
    serialized = json.dumps(payload, ensure_ascii=False, indent=2)
    if context.reason is SqlRepairReason.DATE_FILTER_CONFIGURATION:
        guidance = (
            "固定语义 metric 不得返回 date_filter；可变时间图表必须让 SQL 使用与 "
            "date_parameter_type 匹配的看板日期 token，并让 time_field 对应实际过滤字段；"
            "date_filter 存在时不得使用 CURDATE、CURRENT_DATE、NOW 或同类当前时间函数。\n"
        )
    else:
        guidance = ""
    return (
        "上一版 SQL 未通过校验或执行，请根据下方修复上下文重写完整 SQL JSON。\n"
        "只修复上下文指出的问题，继续遵守当前数据源、权限和 Data Skills 约束，"
        "不得编造表、字段或业务口径。\n"
        + guidance
        + "请仅返回完整 SQL JSON，不要返回解释、Markdown 或局部 SQL。\n"
        + f"```json\n{serialized}\n```"
    )
```

- [x] **Step 4: 写 Smart Q&A 图路由失败测试**

```python
def test_prepare_sql_date_contract_error_queues_repair(monkeypatch):
    service = _service_for_prepare_sql()
    service.check_sql = lambda **_: (_ for _ in ()).throw(
        ChatDateFilterConfigurationError("metric_chart")
    )
    update = smart_qa_graph._prepare_sql(_state(service))
    assert update["sql_repair_pending"] is True
    assert update["sql_repair_context"].reason is SqlRepairReason.DATE_FILTER_CONFIGURATION
```

- [x] **Step 5: 运行图测试并确认当前直接抛错**

Run: `cd backend; ./.venv/Scripts/python.exe -m pytest tests/test_smart_qa_graph.py -k "date_contract_error" -q`

Expected: FAIL，`_prepare_sql` 未接受新的重试原因。

- [x] **Step 6: 将新原因加入 `_prepare_sql` 可重试集合**

```python
if reason not in {
    SqlRepairReason.SQL_RESPONSE_FORMAT,
    SqlRepairReason.DATABASE_SYNTAX_OR_DIALECT,
    SqlRepairReason.DATE_FILTER_CONFIGURATION,
}:
    raise
```

- [x] **Step 7: 运行目标回归**

Run: `cd backend; ./.venv/Scripts/python.exe -m pytest tests/test_sql_repair.py tests/test_smart_qa_graph.py tests/test_chat_dashboard_date_filter.py -q`

Expected: 全部 PASS。

### Task 2: 清理并发布 flam/修仙工作空间 Data Skill

**Files:**
- Create: `tools/dashboard_date_contract.py`
- Modify: `tools/seed_xiuxian_data_skills.py`
- Modify: `tools/seed_flam_first_zombie_data_skills.py`
- Test: `backend/tests/test_xiuxian_data_skill_seed.py`
- Test: `backend/tests/test_flam_first_zombie_data_skill_seed.py`
- Runtime backup: `.codex-runtime/data-skill-backups/ai-dashboard-date-contract-20260730.json`

**Interfaces:**
- Consumes: 两个 seed 的现有幂等 upsert、精确 tenant/datasource 作用域与 embedding 刷新。
- Produces: 对可变时间 SQL 明确使用 dashboard token、对固定 metric 明确省略 `date_filter` 的实际空间级 prompt。

- [x] **Step 1: 写两个 seed 的失败契约测试**

```python
def assert_dashboard_date_contract(prompt: str) -> None:
    assert "{{dashboard_start_yyyymmdd}}" in prompt
    assert "{{dashboard_end_yyyymmdd}}" in prompt
    assert "固定语义 `metric`" in prompt
    assert "不得返回 `date_filter`" in prompt
    assert "`time_field` 必须对应 SQL 中实际参数化字段" in prompt


def test_xiuxian_date_skill_contains_dashboard_date_contract() -> None:
    assert_dashboard_date_contract(_date_skill()["prompt"])


def test_all_flam_analysis_skills_contain_dashboard_date_contract() -> None:
    for skill in seed.DATA_SKILLS:
        assert_dashboard_date_contract(skill["prompt"])
```

- [x] **Step 2: 运行测试并确认缺少工作空间级契约**

Run: `cd backend; ./.venv/Scripts/python.exe -m pytest tests/test_xiuxian_data_skill_seed.py tests/test_flam_first_zombie_data_skill_seed.py -k "dashboard_date_contract" -q`

Expected: FAIL，prompt 缺少至少一个明确约束。

- [x] **Step 3: 增加统一、短小的工作空间级日期输出段并附加到 seed prompt**

```python
DASHBOARD_DATE_CONTRACT = """## AI 看板日期输出契约
- 固定语义 `metric` 保留问题自身日期，但不得返回 `date_filter` 或看板日期 token。
- 其他包含日期字段的图表必须返回 `date_filter`，SQL 使用 `{{dashboard_start_yyyymmdd}}` 与 `{{dashboard_end_yyyymmdd}}`。
- `time_field` 必须对应 SQL 中实际参数化字段，`date_parameter_type` 必须与 token 家族一致。
- 返回 `date_filter` 时不得使用 `CURDATE()`、`CURRENT_DATE`、`NOW()` 或同类函数。
""".strip()
```

将该段放在每条最终 prompt 的末尾，使其优先于前面的历史 SQL 示例；修仙可变日期和日期骨架示例同时替换为 token，固定最新完整日 metric 示例保留并标注不返回 `date_filter`。

- [x] **Step 4: 更新原有 CURDATE 断言并运行 seed 全量测试**

Run: `cd backend; ./.venv/Scripts/python.exe -m pytest tests/test_xiuxian_data_skill_seed.py tests/test_flam_first_zombie_data_skill_seed.py tests/test_platform_sql_data_skill_migration.py -q`

Expected: 全部 PASS，prompt 长度仍不超过 `MAX_PROMPT_CHARS=18000`。

- [x] **Step 5: 备份实际数据库中两个作用域的 Data Skill**

Run: 使用只读 SQL 导出 `custom_prompt` 中 tenant/datasource 精确匹配的记录到 `.codex-runtime/data-skill-backups/ai-dashboard-date-contract-20260730.json`。

Expected: 备份包含记录 ID、tenant、datasource_ids、name、description、prompt 与更新时间，不包含无关空间记录。

- [ ] **Step 6: 幂等发布并回读**

Run:

```powershell
./backend/.venv/Scripts/python.exe tools/seed_flam_first_zombie_data_skills.py
./backend/.venv/Scripts/python.exe tools/seed_xiuxian_data_skills.py
```

Expected: 两个脚本退出码为 0；数据库回读确认 datasource `3`、`6` 的目标 prompt 含新契约，embedding signature 已更新。

### Task 3: 本地运行与真实 UI 验收

**Files:**
- Evidence: `.codex-runtime/ai-dashboard-date-contract-retest-20260730/`

**Interfaces:**
- Consumes: 最新代码、已发布 Data Skill、本地 API/Worker 相同独立队列。
- Produces: 三类原失败的真实 UI 复测记录与最终分类。

- [ ] **Step 1: 重启并核对完整本地栈**

Run:

```powershell
./tools/stack-local.ps1 -Action restart -BackendPorts 8000 -StartMcp -SkipDatabase -SkipRedis -SkipNginx
```

另行确认前端 `5173`，并核对 API `8000`、MCP `8001`、Worker 队列以及 LLM 配置 `120/900/1`。

- [ ] **Step 2: 通过真实 UI 提交代表问题**

覆盖：flam 实时趋势、flam 出征趋势、flam 留存趋势、修仙留存趋势、修仙固定本月 metric、修仙今日实时 metric。每题记录 workspace、datasource、record_id、最终 SQL、图表类型、错误和耗时。

- [ ] **Step 3: 核对持久化与执行边界**

Expected:

- 可变时间图表的 `chat_record.sql` 保留 token，执行日志 SQL 已渲染实际日期。
- 固定 metric 的原始 JSON 和持久配置不包含 `date_filter`。
- 不出现三类日期契约错误；其他 SQL、图表或超时问题单独分类。

- [ ] **Step 4: 运行最终自动化验证与差异检查**

Run:

```powershell
cd backend
./.venv/Scripts/python.exe -m pytest tests/test_sql_repair.py tests/test_smart_qa_graph.py tests/test_chat_dashboard_date_filter.py tests/test_xiuxian_data_skill_seed.py tests/test_flam_first_zombie_data_skill_seed.py -q
cd ..
git diff --check
git status --short
```

Expected: 目标测试全部 PASS、`git diff --check` 无错误；只保留本计划明确涉及的源码、测试、计划文档变更和未跟踪运行证据。
