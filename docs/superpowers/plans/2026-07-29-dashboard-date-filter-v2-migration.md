# 看板日期筛选 V2 与显式迁移 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将看板日期参数从透视配置中彻底拆分为版本化 `dateFilter`，修复永久错误无限加载，并以可审计、可回滚的方式迁移存量图表。

**Architecture:** `canvas_view_info` 继续作为图表配置载体，但 SQL 图表统一写出 `configVersion=2`、独立 `dateFilter` 和纯透视 `pivot`。后端执行链先解析 V2 或受控 V1，再渲染日期、校验权限与 SQL、执行原始查询并按需透视；前端使用统一配置规范化器、请求构造器和有限状态机。存量迁移通过显式清单、预演、数据库审计快照、CAS 更新、读回验证和条件回滚完成。

**Tech Stack:** Python 3.11、FastAPI、Pydantic、SQLModel、SQLAlchemy/Alembic、PostgreSQL、Pytest、Vue 3、TypeScript、Element Plus Secondary、Node `assert`、Vite。

## Global Constraints

- 正常图表的日期入口位置、日期面板、透视控件、卡片布局、图表字段映射和操作方式不得改变。
- 日期筛选与透视独立：关闭 `pivot.enabled` 只能关闭透视，不得删除或禁用 `dateFilter`。
- V2 持久化字段固定为 `configVersion=2`、`dateFilter.enabled`、`dateFilter.parameterType`、`dateFilter.expression`；V2 的 `pivot` 不得出现 `date_parameter_type` 或 `date_expression`。
- 日期参数类型只允许 `date`、`yyyymmdd_number`、`yyyymmdd_text`、`timestamp`。
- SQL 含受控日期 token 时必须存在完整、匹配的 `dateFilter`；不含 token 时不得自动创建日期筛选。
- 禁止根据标题、字段名、第一列、相似字段、历史结果或数据源名称猜测日期语义。
- 只有 `dashboard_query_busy`、超时、网络中断和显式可恢复的数据源连接错误可以自动重试。
- 单次刷新最多重试 3 次，基础退避固定为 2 秒、5 秒、15 秒，并加入不超过 20% 的随机抖动。
- 权限、迁移、配置、透视字段、SQL 安全和只读校验错误均为终态错误，不得自动重试。
- 图表运行状态固定为 `loading`、`ready`、`refreshing`、`stale`、`failed`；请求结束后不得停留在 `loading` 或 `refreshing`。
- 所有 Redis 缓存键必须继续使用现有租户、用户和数据源作用域 helper；不得新增裸键。
- 当前试点固定为租户 `7482727237662281728`、看板 `1752a05a80724b379438838bee516a46`、图表 `2197205356986408960` 和 `2197218114511478784`。
- 两个试点图表属于已人工确认的 `approved_repair`，目标配置固定为 `yyyymmdd_number` 和 `{"version":1,"mode":"preset","preset":"past_7_days"}`。
- 迁移默认使用 `scan` 子命令只预演；写入必须显式使用 `apply --batch-id`，回滚必须显式使用 `rollback --batch-id`，单看板回滚再增加 `--dashboard-id`。
- V1 数量归零后至少观察 7 个自然日才能关闭读取器；关闭后再观察至少 7 个自然日才能删除兼容代码。
- 每个任务独立提交、独立评审、独立部署；不得把状态修复、V2 写入、数据迁移和 V1 删除捆绑成一次发布。
- 不触碰工作区内与本任务无关的未跟踪 SQL 分析文件。

---

## 文件职责映射

### 后端

- Create: `backend/apps/dashboard/models/dashboard_chart_config.py`：V2 持久化模型、API 日期请求模型、规范化结果和稳定错误类型。
- Create: `backend/apps/dashboard/crud/dashboard_date_filter_legacy.py`：迁移期唯一的 V1 确定性读取器及开关。
- Modify: `backend/apps/dashboard/crud/dashboard_date_filter.py`：只负责 token 扫描、日期表达式解析、方言渲染和能力计算，不再读取 `pivot`。
- Modify: `backend/apps/dashboard/models/dashboard_model.py`：`DashboardSqlPreview.date_filter` 请求字段、迁移审计 SQLModel。
- Modify: `backend/apps/dashboard/crud/dashboard_service.py`：执行顺序、稳定错误类型、V2 缓存键、画布写入校验、复制和模板路径。
- Create: `backend/alembic/versions/150_dashboard_date_filter_migration_audit.py`：迁移审计表及索引。
- Create: `backend/apps/dashboard/crud/dashboard_date_filter_migration.py`：扫描、分类、预演、CAS、审计、验证和回滚纯业务服务。
- Create: `tools/dashboard_date_filter_v2_migration.py`：显式命令行入口，默认预演。
- Create: `tools/dashboard_date_filter_v2_manifests/2026-07-29-workspace-7482727237662281728.json`：当前工作空间人工批准修复清单。

### 前端

- Create: `frontend/src/views/dashboard/utils/dashboardChartConfig.ts`：所有写入入口共享的 V2 规范化和校验。
- Modify: `frontend/src/views/dashboard/utils/dashboardDateFilter.ts`：独立 `date_filter` 请求构造和页面会话日期状态。
- Modify: `frontend/src/views/dashboard/utils/dashboardPermissionRefresh.ts`：终态/瞬态白名单、有限退避和图表状态转换。
- Modify: `frontend/src/views/dashboard/common/DashboardSqlEditor.vue`：编辑器读取和写入独立 `dateFilter`，保持现有控件 DOM 与样式。
- Modify: `frontend/src/views/dashboard/editor/ChatChartSelection.vue`：智能问答转存写出 V2。
- Modify: `frontend/src/views/chat/chat-block/ChartBlock.vue`：聊天图表转存写出 V2。
- Modify: `frontend/src/views/dashboard/components/sq-view/index.vue`：日期请求与透视请求拆分，保持现有交互。
- Modify: `frontend/src/views/dashboard/preview/SQPreviewShow.vue`：预览页有限状态机和有限重试。
- Modify: `frontend/src/views/dashboard/editor/index.vue`：编辑页有限状态机和有限重试。
- Modify: `frontend/src/views/dashboard/preview/SQComponentWrapper.vue`：单图刷新使用独立 `date_filter`。
- Modify: `frontend/src/i18n/zh-CN.json`、`zh-TW.json`、`en.json`、`ko-KR.json`：只增加异常终态文案，不改正常界面文案。

### 测试与运维文档

- Create: `tests/test_dashboard_chart_config_v2.py`：V2 模型、V1 读取和画布规范化测试。
- Modify: `tests/test_dashboard_date_filter.py`：独立日期执行器组合测试。
- Modify: `tests/test_dashboard_service.py`：API、透视组合、稳定错误和缓存键测试。
- Modify: `backend/tests/test_dashboard_permission_cache.py`：租户/用户/数据源/日期/透视缓存隔离。
- Create: `backend/tests/test_dashboard_date_filter_migration.py`：迁移分类、幂等、CAS、审计和回滚测试。
- Modify: `frontend/src/views/dashboard/utils/dashboardPermissionRefresh.test.mjs`：错误白名单和退避测试。
- Create: `frontend/src/views/dashboard/utils/dashboardChartConfig.test.mjs`：V2 单写及关闭透视不丢日期测试。
- Modify: 现有各入口 `.test.mjs`：编辑、转存、预览、日期交互和 UI 结构回归。
- Create: `docs/dashboard_date_filter_v2_rollout.md`：指标、灰度、暂停、回滚和 V1 删除门禁。

---

### Task 1: 终止永久错误的自动重试

**Files:**
- Modify: `frontend/src/views/dashboard/utils/dashboardPermissionRefresh.ts`
- Modify: `frontend/src/views/dashboard/utils/dashboardPermissionRefresh.test.mjs`
- Modify: `frontend/src/views/dashboard/preview/SQPreviewShow.vue:624`
- Modify: `frontend/src/views/dashboard/editor/index.vue:454`

**Interfaces:**
- Consumes: 后端结果 `{status, error_type, recoverable?}`、是否存在当前用户可用快照、当前重试序号。
- Produces: `classifyDashboardChartFailure(...) -> 'terminal' | 'transient' | 'none'`、`nextDashboardChartRetryDelayMs(...) -> number | null`、`resolveDashboardChartRenderState(...) -> DashboardChartRenderState`。

- [ ] **Step 1: 扩展失败测试，锁定终态和瞬态边界**

```javascript
assert.equal(classifyDashboardChartFailure(
  { status: 'failed', error_type: 'dashboard_date_filter_unconfigured' }
), 'terminal')
assert.equal(classifyDashboardChartFailure(
  { status: 'failed', error_type: 'dashboard_query_busy' }
), 'transient')
assert.equal(classifyDashboardChartFailure(
  { status: 'failed', error_type: 'datasource_connection_failed', recoverable: true }
), 'transient')
assert.equal(classifyDashboardChartFailure(
  { status: 'failed', error_type: 'query_failed' }
), 'terminal')
assert.equal(nextDashboardChartRetryDelayMs(0, () => 0.5), 2000)
assert.equal(nextDashboardChartRetryDelayMs(1, () => 0.5), 5000)
assert.equal(nextDashboardChartRetryDelayMs(2, () => 0.5), 15000)
assert.equal(nextDashboardChartRetryDelayMs(3, () => 0.5), null)
assert.equal(resolveDashboardChartRenderState({ phase: 'refreshing', failed: true, hasSnapshot: true }), 'stale')
assert.equal(resolveDashboardChartRenderState({ phase: 'loading', failed: true, hasSnapshot: false }), 'failed')
```

- [ ] **Step 2: 运行测试并确认现有宽泛策略失败**

Run from `frontend`:

```powershell
node src/views/dashboard/utils/dashboardPermissionRefresh.test.mjs
```

Expected: FAIL，当前 `query_failed` 被错误识别为可重试，且没有 2/5/15 秒退避与终态状态函数。

- [ ] **Step 3: 实现白名单分类和可测试抖动**

```typescript
export type DashboardChartRenderState = 'loading' | 'ready' | 'refreshing' | 'stale' | 'failed'
export type DashboardFailureClass = 'none' | 'terminal' | 'transient'

export type DashboardRefreshResult = {
  status?: unknown
  error_type?: unknown
  recoverable?: unknown
}

const TRANSIENT_ERROR_TYPES = new Set([
  'dashboard_query_busy',
  'request_timeout',
  'network_error',
  'datasource_connection_failed',
])
const RETRY_DELAYS_MS = [2000, 5000, 15000] as const

export function classifyDashboardChartFailure(result: DashboardRefreshResult): DashboardFailureClass {
  if (result?.status !== 'failed') return 'none'
  const errorType = String(result?.error_type || '')
  if (!TRANSIENT_ERROR_TYPES.has(errorType)) return 'terminal'
  if (errorType === 'datasource_connection_failed' && result?.recoverable !== true) return 'terminal'
  return 'transient'
}

export function nextDashboardChartRetryDelayMs(
  retryIndex: number,
  random: () => number = Math.random
): number | null {
  const base = RETRY_DELAYS_MS[retryIndex]
  if (base === undefined) return null
  const jitter = (Math.min(1, Math.max(0, random())) * 0.4) - 0.2
  return Math.round(base * (1 + jitter))
}

export function resolveDashboardChartRenderState(input: {
  phase: 'loading' | 'refreshing'
  failed: boolean
  hasSnapshot: boolean
}): DashboardChartRenderState {
  if (!input.failed) return 'ready'
  return input.hasSnapshot ? 'stale' : 'failed'
}
```

同时把 `DashboardRefreshResult` 增加 `recoverable?: unknown`，并让原 `shouldRetryDashboardChartFailure` 仅委托给 `classifyDashboardChartFailure(result) === 'transient'`。

- [ ] **Step 4: 接入预览页和编辑页，不改变模板结构**

将两个页面的固定 `4000ms / 6 次` 替换为每张刷新轮次的 `retryIndex` 与 `nextDashboardChartRetryDelayMs`。终态失败时：有快照写入 `viewInfo.dataState='stale'` 并保留数据，无快照调用现有 `applyChartResult` 写入 `failed`；瞬态失败才进入下一次调度。保持现有请求版本和 `AbortController` 检查。

```typescript
const failureClass = classifyDashboardChartFailure(result)
if (failureClass === 'transient') {
  transientPendingCount += 1
} else {
  applyTerminalDashboardChartFailure(viewInfo, result, hasUsableChartSnapshot(viewInfo))
}

const delay = transientPendingCount > 0
  ? nextDashboardChartRetryDelayMs(chartRefreshRetryCount)
  : null
if (delay !== null) {
  chartRefreshRetryCount += 1
  scheduleDashboardChartRefresh(loadVersion, delay)
}
```

- [ ] **Step 5: 运行前端回归并提交**

```powershell
node src/views/dashboard/utils/dashboardPermissionRefresh.test.mjs
node src/views/dashboard/preview/SQPreviewShow.permission-refresh.test.mjs
node src/views/dashboard/editor/index.permission-refresh.test.mjs
git add -- frontend/src/views/dashboard/utils/dashboardPermissionRefresh.ts frontend/src/views/dashboard/utils/dashboardPermissionRefresh.test.mjs frontend/src/views/dashboard/preview/SQPreviewShow.vue frontend/src/views/dashboard/editor/index.vue
git commit -m "修复：终止看板永久错误无限重试"
```

Expected: 测试全部 PASS；终态错误请求次数为 1，瞬态错误最多为首次请求加 3 次重试。

---

### Task 2: 定义 V2 配置和受控 V1 读取器

**Files:**
- Create: `backend/apps/dashboard/models/dashboard_chart_config.py`
- Create: `backend/apps/dashboard/crud/dashboard_date_filter_legacy.py`
- Create: `tests/test_dashboard_chart_config_v2.py`
- Modify: `backend/common/core/config.py`

**Interfaces:**
- Produces: `DashboardDateFilterConfig`、`DashboardDateFilterRequest`、`DashboardChartConfigResolution`、`resolve_dashboard_chart_date_filter(view_info, allow_legacy) -> DashboardChartConfigResolution`。
- Consumes: 单个图表 `view_info` 及 SQL token 扫描结果。

- [ ] **Step 1: 写 V2、完整 V1 和不完整 V1 的失败测试**

```python
def test_v2_date_filter_is_independent_from_disabled_pivot():
    result = resolve_dashboard_chart_date_filter({
        "configVersion": 2,
        "sql": "select * from t where dt between {{dashboard_start_yyyymmdd}} and {{dashboard_end_yyyymmdd}}",
        "dateFilter": {
            "enabled": True,
            "parameterType": "yyyymmdd_number",
            "expression": {"version": 1, "mode": "preset", "preset": "past_7_days"},
        },
        "pivot": {"enabled": False},
    }, allow_legacy=True)
    assert result.status == "v2"
    assert result.date_filter.parameter_type == "yyyymmdd_number"

def test_complete_v1_is_deterministically_read_but_not_persisted():
    result = resolve_dashboard_chart_date_filter({
        "sql": "select * from t where dt between {{dashboard_start_yyyymmdd}} and {{dashboard_end_yyyymmdd}}",
        "pivot": {
            "enabled": False,
            "date_parameter_type": "yyyymmdd_number",
            "date_expression": {"version": 1, "mode": "preset", "preset": "past_7_days"},
        },
    }, allow_legacy=True)
    assert result.status == "legacy"

def test_incomplete_v1_requires_explicit_migration():
    result = resolve_dashboard_chart_date_filter({
        "sql": "select * from t where dt between {{dashboard_start_yyyymmdd}} and {{dashboard_end_yyyymmdd}}",
        "pivot": {"enabled": False},
    }, allow_legacy=True)
    assert result.status == "migration_required"
    assert result.error_type == "dashboard_date_filter_migration_required"
```

- [ ] **Step 2: 运行测试并确认模块不存在**

```powershell
backend\.venv\Scripts\python.exe -m pytest tests/test_dashboard_chart_config_v2.py -q
```

Expected: FAIL，`dashboard_chart_config` 和 `dashboard_date_filter_legacy` 尚未定义。

- [ ] **Step 3: 实现 Pydantic 契约**

```python
from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

DateParameterType = Literal["date", "yyyymmdd_number", "yyyymmdd_text", "timestamp"]

class DashboardDateFilterConfig(BaseModel):
    enabled: bool = True
    parameter_type: DateParameterType = Field(alias="parameterType")
    expression: dict[str, Any]
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

class DashboardDateFilterRequest(BaseModel):
    parameter_type: DateParameterType
    expression: dict[str, Any] | None = None
    custom_start: str = ""
    custom_end: str = ""
    model_config = ConfigDict(extra="forbid")

@dataclass(frozen=True)
class DashboardChartConfigResolution:
    status: Literal["none", "v2", "legacy", "migration_required", "invalid"]
    date_filter: DashboardDateFilterRequest | None
    error_type: str = ""
    reason: str = ""
```

使用 `model_dump(by_alias=True)` 持久化驼峰字段；API 使用蛇形字段。表达式继续交给现有 `resolve_dashboard_date_expression` 做版本与范围校验，不在模型层复制规则。

- [ ] **Step 4: 实现唯一 V1 读取器和开关**

```python
def read_legacy_dashboard_date_filter(view_info: Mapping[str, Any]) -> DashboardChartConfigResolution:
    pivot = view_info.get("pivot") if isinstance(view_info.get("pivot"), dict) else {}
    parameter_type = pivot.get("date_parameter_type")
    expression = pivot.get("date_expression")
    if parameter_type is None or expression is None:
        return DashboardChartConfigResolution(
            status="migration_required",
            date_filter=None,
            error_type="dashboard_date_filter_migration_required",
            reason="incomplete_legacy_date_filter",
        )
    try:
        request = DashboardDateFilterRequest(
            parameter_type=parameter_type,
            expression=expression,
        )
    except ValidationError:
        return DashboardChartConfigResolution(
            status="invalid",
            date_filter=None,
            error_type="dashboard_date_filter_invalid_template",
            reason="invalid_legacy_date_filter",
        )
    return DashboardChartConfigResolution(status="legacy", date_filter=request)
```

在 `Settings` 增加 `DASHBOARD_DATE_FILTER_V1_READ_ENABLED: bool = True`。`resolve_dashboard_chart_date_filter` 只有在 SQL 正文存在受控 token 且 V2 不存在时才调用该读取器；开关关闭时返回 `dashboard_date_filter_migration_required`，不得补默认类型或表达式。

- [ ] **Step 5: 运行测试并提交**

```powershell
backend\.venv\Scripts\python.exe -m pytest tests/test_dashboard_chart_config_v2.py tests/test_dashboard_date_filter.py -q
git add -- backend/apps/dashboard/models/dashboard_chart_config.py backend/apps/dashboard/crud/dashboard_date_filter_legacy.py backend/common/core/config.py tests/test_dashboard_chart_config_v2.py
git commit -m "功能：定义看板日期筛选 V2 契约"
```

Expected: PASS；完整 V1 只转换到内存，不完整 V1 明确进入迁移终态。

---

### Task 3: 拆分后端日期执行与透视执行

**Files:**
- Modify: `backend/apps/dashboard/models/dashboard_model.py:406`
- Modify: `backend/apps/dashboard/crud/dashboard_date_filter.py:318`
- Modify: `backend/apps/dashboard/crud/dashboard_service.py:1925`
- Modify: `backend/apps/dashboard/crud/dashboard_service.py:1962`
- Modify: `backend/apps/dashboard/crud/dashboard_service.py:5266`
- Modify: `tests/test_dashboard_date_filter.py`
- Modify: `tests/test_dashboard_service.py`
- Modify: `backend/tests/test_dashboard_permission_cache.py`

**Interfaces:**
- Consumes: `DashboardSqlPreview.date_filter: DashboardDateFilterRequest | None` 与纯透视 `DashboardPivotRequest`。
- Produces: `prepare_dashboard_date_filter(sql, ds_type, date_filter, today) -> DashboardDateFilterPreparation`；稳定 `error_type`；含日期与透视双维度的缓存键。

- [ ] **Step 1: 写日期/透视四组合与终态错误测试**

```python
@pytest.mark.parametrize(("pivot_enabled", "expected_pivot_calls"), [(False, 0), (True, 1)])
def test_preview_renders_v2_date_filter_independently_from_pivot(pivot_enabled, expected_pivot_calls, monkeypatch):
    request = DashboardSqlPreview(
        datasource=1,
        sql="select dt, amount from orders where dt between {{dashboard_start_yyyymmdd}} and {{dashboard_end_yyyymmdd}}",
        date_filter=DashboardDateFilterRequest(
            parameter_type="yyyymmdd_number",
            expression={"version": 1, "mode": "preset", "preset": "past_7_days"},
        ),
        pivot=DashboardPivotRequest(enabled=pivot_enabled, time_field="dt", metric_field="amount"),
    )
    result = dashboard_service.preview_sql(_session(), _user(), request)
    assert result["status"] == "success"
    assert result["executed_sql"].count("{{dashboard_") == 0
    assert _pivot_call_count() == expected_pivot_calls

def test_preview_missing_v2_date_filter_does_not_execute(monkeypatch):
    execute = monkeypatch.spy(sql_executor, "exec_sql")
    result = dashboard_service.preview_sql(_session(), _user(), DashboardSqlPreview(
        datasource=1,
        sql="select * from orders where dt >= {{dashboard_start_yyyymmdd}}",
    ))
    assert result["status"] == "failed"
    assert result["error_type"] == "dashboard_date_filter_unconfigured"
    assert execute.call_count == 0
```

补充缓存测试：相同 SQL 在不同 `tenant/user/datasource/parameter_type/resolved_start/resolved_end/pivot` 下 key 不同；关闭透视不能移除日期范围维度。

- [ ] **Step 2: 运行聚焦测试并确认失败**

```powershell
backend\.venv\Scripts\python.exe -m pytest tests/test_dashboard_date_filter.py tests/test_dashboard_service.py -k "date_filter or pivot" -q
backend\.venv\Scripts\python.exe -m pytest backend/tests/test_dashboard_permission_cache.py -k "cache_key" -q
```

Expected: FAIL，API 仍从 `pivot` 读取日期字段。

- [ ] **Step 3: 修改请求模型并收窄透视模型**

```python
class DashboardPivotRequest(BaseModel):
    enabled: bool = False
    client_filter_only: bool = False
    time_field: str = ""
    metric_field: str = ""
    metric_fields: list[str] = Field(default_factory=list)
    metric_aggregations: dict[str, Literal["sum", "avg", "min", "max", "count"]] = Field(default_factory=dict)
    group_field: str = ""
    group_enabled: bool = True
    group_values: list[str] = Field(default_factory=list)
    dimensions: list[dict[str, Any]] = Field(default_factory=list)
    range_enabled: bool = True
    granularity: Literal["day", "week", "month"] = "day"
    range: Literal["source", "7d", "14d", "30d", "90d", "all", "custom"] = "source"
    custom_start: str = ""
    custom_end: str = ""
    aggregation: Literal["sum", "avg", "min", "max", "count"] = "sum"

class DashboardSqlPreview(BaseModel):
    datasource: int
    sql: str = ""
    pivot: DashboardPivotRequest | None = None
    cache_only: bool = False
    force_refresh: bool = False
    date_filter: DashboardDateFilterRequest | None = None
```

删除 `DashboardPivotRequest.date_parameter_type` 和 `date_expression`。迁移期旧前端请求只通过图表加载链的 V1 读取器转换，`/sql_preview` 新请求不再接受透视中的日期字段。

- [ ] **Step 4: 修改日期执行器签名和执行顺序**

```python
def prepare_dashboard_date_filter(
    sql: str,
    *,
    ds_type: str | None,
    date_filter: DashboardDateFilterRequest | None,
    today: date | None = None,
) -> DashboardDateFilterPreparation:
    source_sql = str(sql or "")
    physical_tables = _extract_tables_with_tokens_masked(source_sql, ds_type)
    if _is_realtime_table(physical_tables):
        return _realtime(source_sql, physical_tables)
    if not has_dashboard_date_filter_parameters(source_sql):
        return _not_applicable(source_sql, physical_tables)
    if date_filter is None:
        return _unconfigured(source_sql, physical_tables, "missing_date_filter")
    parameter_error = validate_dashboard_date_parameter_sql(source_sql, date_filter.parameter_type)
    if parameter_error:
        return _unconfigured(source_sql, physical_tables, parameter_error)
    return _resolve_and_render(source_sql, physical_tables, date_filter, ds_type, today)
```

`_prepare_dashboard_chart_query` 和 `_prepare_dashboard_chart_item_query` 从 `view_info` 解析 V2/V1，然后把 `date_filter` 与 `pivot` 分别传入；`preview_sql` 直接使用请求的 `date_filter`。顺序固定为权限与数据源上下文校验、日期渲染、SQL 安全校验、原始查询、可选透视。

- [ ] **Step 5: 固定稳定错误映射和缓存键**

```python
DATE_FILTER_ERROR_TYPES = {
    "migration_required": "dashboard_date_filter_migration_required",
    "missing_date_filter": "dashboard_date_filter_unconfigured",
    "invalid_parameter_type": "dashboard_date_filter_invalid_template",
    "parameter_type_mismatch": "dashboard_date_filter_invalid_template",
    "incomplete_parameters": "dashboard_date_filter_invalid_template",
    "invalid_date_expression": "dashboard_date_filter_invalid_template",
}
```

缓存 key 输入增加规范化后的 `parameter_type`、`resolved_start`、`resolved_end`、日期表达式哈希和纯透视配置哈希；结构化日志只记录 SQL 指纹，不记录完整 SQL 或查询结果。

能力响应继续返回 `defaultStart/defaultEnd` 作为平台无表达式时的默认 14 天，并明确返回当前持久化表达式实际解析出的 `resolvedStart/resolvedEnd`。前端日期面板初始化优先使用 `resolvedStart/resolvedEnd`，因此 `past_7_days` 首次展示和首次 SQL 都是同一 7 天范围。

- [ ] **Step 6: 运行回归并提交**

```powershell
backend\.venv\Scripts\python.exe -m pytest tests/test_dashboard_date_filter.py tests/test_dashboard_service.py backend/tests/test_dashboard_permission_cache.py backend/tests/test_dashboard_execution_datasource.py -q
git add -- backend/apps/dashboard/models/dashboard_model.py backend/apps/dashboard/crud/dashboard_date_filter.py backend/apps/dashboard/crud/dashboard_service.py tests/test_dashboard_date_filter.py tests/test_dashboard_service.py backend/tests/test_dashboard_permission_cache.py
git commit -m "重构：拆分看板日期与透视执行"
```

Expected: PASS；透视关闭时日期仍被渲染，配置错误不调用业务数据源。

---

### Task 4: 建立前端 V2 单写规范化器

**Files:**
- Create: `frontend/src/views/dashboard/utils/dashboardChartConfig.ts`
- Create: `frontend/src/views/dashboard/utils/dashboardChartConfig.test.mjs`
- Modify: `frontend/src/views/dashboard/utils/dashboardDateFilter.ts`

**Interfaces:**
- Consumes: 当前 `viewInfo`、SQL、日期参数类型、日期表达式、用户临时范围。
- Produces: `normalizeDashboardChartConfigV2(...)`、`buildDashboardDateFilterRequest(...)`、`buildAppliedDashboardDateFilterRequest(...)`。

- [ ] **Step 1: 写单写、禁猜测和透视解耦测试**

```javascript
const migrated = normalizeDashboardChartConfigV2({
  sql: 'select * from t where dt between {{dashboard_start_yyyymmdd}} and {{dashboard_end_yyyymmdd}}',
  pivot: {
    enabled: false,
    date_parameter_type: 'yyyymmdd_number',
    date_expression: { version: 1, mode: 'preset', preset: 'past_7_days' },
  },
})
assert.equal(migrated.configVersion, 2)
assert.equal(migrated.dateFilter.parameterType, 'yyyymmdd_number')
assert.deepEqual(migrated.pivot, { enabled: false })

assert.throws(() => normalizeDashboardChartConfigV2({
  sql: 'select * from t where dt >= {{dashboard_start_yyyymmdd}}',
  pivot: { enabled: false },
}), /dashboard_date_filter_migration_required/)

const disabled = withDashboardPivotEnabled(migrated, false)
assert.deepEqual(disabled.dateFilter, migrated.dateFilter)
```

- [ ] **Step 2: 运行测试并确认模块不存在**

```powershell
node src/views/dashboard/utils/dashboardChartConfig.test.mjs
```

Expected: FAIL，V2 规范化器尚未定义。

- [ ] **Step 3: 实现 V2 规范化与清理**

```typescript
import {
  dashboardDateParameterTokens,
  scanDashboardDateParameterTokens,
} from './dashboardDateFilter.ts'

type DashboardDateParameterType = keyof typeof dashboardDateParameterTokens
type DashboardDateFilterConfig = {
  enabled: boolean
  parameterType: DashboardDateParameterType
  expression: Record<string, unknown>
}

export class DashboardChartConfigError extends Error {
  constructor(public readonly errorType: string) {
    super(errorType)
  }
}

function isRecord(value: unknown): value is Record<string, any> {
  return Boolean(value && typeof value === 'object' && !Array.isArray(value))
}

function validateDashboardDateFilter(tokens: string[], configured: Record<string, any>) {
  const parameterType = String(configured.parameterType || '') as DashboardDateParameterType
  const expected = dashboardDateParameterTokens[parameterType]
  if (!expected || configured.enabled === false || !isRecord(configured.expression)) {
    throw new DashboardChartConfigError('dashboard_date_filter_invalid_template')
  }
  const completeRange = tokens.length === 2 && expected.every((token) => tokens.includes(token))
  const endOnly = tokens.length === 1 && tokens[0] === expected[1]
  if (!completeRange && !endOnly) {
    throw new DashboardChartConfigError('dashboard_date_filter_invalid_template')
  }
}

function cleanPivot(pivot: Record<string, any>) {
  const { date_parameter_type, date_expression, ...cleaned } = pivot
  return cleaned
}

function completeLegacyDateFilter(pivot: Record<string, any>, tokens: string[]) {
  if (!pivot.date_parameter_type && !pivot.date_expression) return undefined
  if (!pivot.date_parameter_type || !pivot.date_expression) {
    throw new DashboardChartConfigError('dashboard_date_filter_migration_required')
  }
  const configured = {
    enabled: true,
    parameterType: String(pivot.date_parameter_type),
    expression: structuredClone(pivot.date_expression),
  }
  validateDashboardDateFilter(tokens, configured)
  return configured
}

export function normalizeDashboardChartConfigV2(viewInfo: Record<string, any>) {
  const next = structuredClone(viewInfo)
  const tokens = scanDashboardDateParameterTokens(String(next.sql || ''))
  const legacyPivot = isRecord(next.pivot) ? next.pivot : { enabled: false }
  const configured = isRecord(next.dateFilter)
    ? next.dateFilter
    : completeLegacyDateFilter(legacyPivot, tokens)
  if (tokens.length > 0 && !configured) {
    throw new DashboardChartConfigError('dashboard_date_filter_migration_required')
  }
  if (configured) validateDashboardDateFilter(tokens, configured)
  next.configVersion = 2
  next.dateFilter = configured
    ? {
        enabled: configured.enabled !== false,
        parameterType: configured.parameterType,
        expression: structuredClone(configured.expression),
      }
    : undefined
  next.pivot = cleanPivot(legacyPivot)
  if (!next.dateFilter) delete next.dateFilter
  return next
}
```

`completeLegacyDateFilter` 仅在旧 `date_parameter_type` 和 `date_expression` 同时合法、token 家族匹配时返回配置；任一缺失均抛出迁移错误。不得选择第一个 token 类型或默认表达式。

- [ ] **Step 4: 将临时日期范围从 pivot 请求移出**

```typescript
export type DashboardDateFilterCapability = {
  status?: DashboardDateCapabilityStatus | string
  defaultStart?: string
  defaultEnd?: string
  resolvedStart?: string
  resolvedEnd?: string
  maxEnd?: string
  parameterType?: string
  reason?: string
}

export function createDashboardDateFilterState(
  capability: DashboardDateFilterCapability | null | undefined,
  today?: string
): DashboardDateFilterState {
  const configuredRange: DashboardDateRange = [
    String(capability?.resolvedStart || capability?.defaultStart || ''),
    String(capability?.resolvedEnd || capability?.defaultEnd || ''),
  ]
  const initialRange = isValidRange(configuredRange)
    ? configuredRange
    : defaultDashboardDateRange(today)
  return {
    draftRange: copyRange(initialRange),
    appliedRange: copyRange(initialRange),
    pendingRange: null,
    applying: false,
    applyError: '',
  }
}

export function buildDashboardDateFilterRequest(
  viewInfo: { dateFilter?: DashboardDateFilterConfig | null },
  range: DashboardDateRange
) {
  const config = viewInfo.dateFilter
  if (!config?.enabled) return undefined
  return {
    parameter_type: config.parameterType,
    expression: structuredClone(config.expression),
    custom_start: range[0],
    custom_end: range[1],
  }
}

export function buildAppliedDashboardDateFilterRequest(
  viewInfo: {
    dateFilter?: DashboardDateFilterConfig | null
    dateFilterCapability?: DashboardDateFilterCapability | null
  } & object
) {
  const config = viewInfo.dateFilter
  if (!config?.enabled) return undefined
  const state = canShowDashboardDateFilter(viewInfo.dateFilterCapability)
    ? getOrCreateDashboardDateFilterState(viewInfo, viewInfo.dateFilterCapability)
    : null
  return {
    parameter_type: config.parameterType,
    expression: structuredClone(config.expression),
    custom_start: state?.appliedRange[0] || '',
    custom_end: state?.appliedRange[1] || '',
  }
}
```

保留现有 WeakMap 草稿/生效状态；删除 `buildDashboardDatePivot`、`buildAppliedDashboardDatePivot` 和 `buildDashboardDateSourcePreviewPivot`，改为独立请求构造函数。用户临时范围不回写 `canvas_view_info`。

- [ ] **Step 5: 运行测试并提交**

```powershell
node src/views/dashboard/utils/dashboardChartConfig.test.mjs
node src/views/dashboard/preview/SQPreviewShow.date-filter.test.mjs
git add -- frontend/src/views/dashboard/utils/dashboardChartConfig.ts frontend/src/views/dashboard/utils/dashboardChartConfig.test.mjs frontend/src/views/dashboard/utils/dashboardDateFilter.ts
git commit -m "功能：统一看板日期配置 V2 写入"
```

Expected: PASS；关闭透视后 `dateFilter` 结构完全不变。

---

### Task 5: 接入编辑、AI、聊天转存、复制和模板写入

**Files:**
- Modify: `frontend/src/views/dashboard/common/DashboardSqlEditor.vue:3032`
- Modify: `frontend/src/views/dashboard/editor/ChatChartSelection.vue:156`
- Modify: `frontend/src/views/chat/chat-block/ChartBlock.vue:406`
- Modify: `frontend/src/views/dashboard/common/DashboardSqlEditor.date-filter.test.mjs`
- Modify: `frontend/src/views/dashboard/editor/ChatChartSelection.date-control.test.mjs`
- Create: `frontend/src/views/chat/chat-block/ChartBlock.date-filter-v2.test.mjs`
- Modify: `backend/apps/dashboard/crud/dashboard_service.py:145`
- Modify: `backend/tests/test_dashboard_platform_template_snapshot.py`
- Modify: `tests/test_dashboard_service.py`

**Interfaces:**
- Consumes: Task 4 的 `normalizeDashboardChartConfigV2`。
- Produces: 所有新增或保存画布只含 V2；复制和模板路径保留 `dateFilter`、轴、列、洞察、透视、数据源、SQL 和结果数据。

- [ ] **Step 1: 写各入口的失败测试**

在 SQL 编辑器保存测试、智能问答加入看板测试、聊天图表转存测试中分别调用以下完整断言；后端看板复制和平台模板复制使用同一字段集合做 Python 断言：

```javascript
function assertV2DateChart(saved) {
  assert.equal(saved.configVersion, 2)
  assert.deepEqual(saved.dateFilter, {
    enabled: true,
    parameterType: 'yyyymmdd_number',
    expression: { version: 1, mode: 'preset', preset: 'past_7_days' },
  })
  assert.equal(saved.pivot.enabled, false)
  assert.equal('date_parameter_type' in saved.pivot, false)
  assert.equal('date_expression' in saved.pivot, false)
}

assertV2DateChart(sqlEditorSavedView)
assertV2DateChart(chatSelectionSavedView)
assertV2DateChart(chartBlockSavedView)
```

后端复制测试同时断言 `dateFilter`、`chart.columns`、`chart.insight`、`pivot`、`datasource` 和 `sql` 均被保留。

- [ ] **Step 2: 运行入口测试并确认失败**

```powershell
node frontend/src/views/dashboard/common/DashboardSqlEditor.date-filter.test.mjs
node frontend/src/views/dashboard/editor/ChatChartSelection.date-control.test.mjs
node frontend/src/views/chat/chat-block/ChartBlock.date-filter-v2.test.mjs
backend\.venv\Scripts\python.exe -m pytest backend/tests/test_dashboard_platform_template_snapshot.py tests/test_dashboard_service.py -k "canvas or copy or template" -q
```

Expected: FAIL，现有入口仍把日期字段写入 `pivot` 或在 `pivot.enabled=false` 时丢弃配置。

- [ ] **Step 3: 修改 SQL 编辑器，保持控件 DOM 不变**

`initPivotConfig` 只读取纯透视字段；新增 `initDateFilterConfig(viewInfo.dateFilter, viewInfo.pivot)`，仅对完整旧配置做确定性内存转换。`buildPivotConfig` 删除日期字段；新增：

```typescript
function buildDateFilterConfig() {
  if (!dateExpressionEnabled.value) return undefined
  return {
    enabled: true,
    parameterType: form.pivotDateParameterType,
    expression: cloneDashboardDateExpression(sqlBuilder.timeExpression),
  }
}

const normalized = normalizeDashboardChartConfigV2({
  ...props.viewInfo,
  sql: form.sql,
  pivot: buildPivotConfig(),
  dateFilter: buildDateFilterConfig(),
})
Object.assign(props.viewInfo, normalized)
```

现有日期参数类型下拉框、日期表达式选择器、标签、位置和 CSS 不变；变量重命名可以后续单独清理，本任务避免 UI 重构。

- [ ] **Step 4: 修改两个聊天转存入口**

`resolveChartPivot` 只合并透视字段；新增 `resolveChartDateFilter(chartBaseInfo)`：

```typescript
function resolveChartDateFilter(chartBaseInfo: any) {
  if (chartBaseInfo?.configVersion === 2 && chartBaseInfo?.dateFilter) {
    return structuredClone(chartBaseInfo.dateFilter)
  }
  const pivot = chartBaseInfo?.pivot
  if (pivot?.date_parameter_type && pivot?.date_expression) {
    return {
      enabled: true,
      parameterType: pivot.date_parameter_type,
      expression: structuredClone(pivot.date_expression),
    }
  }
  return undefined
}
```

构造 `recordeInfo` 后调用 `normalizeDashboardChartConfigV2`；不完整旧配置必须阻止转存并显示“图表配置待升级”，不能生成 `{enabled:false}` 伪装为有效配置。

- [ ] **Step 5: 后端保存边界实施双读单写**

在 `_sanitize_canvas_view_info` 解析 JSON 后，对每个 SQL 图表调用后端 `normalize_dashboard_chart_config_v2`。完整 V1 确定性转成 V2；不完整 V1 返回 HTTP 422，detail 固定包含 `error_type=dashboard_date_filter_migration_required` 和图表 ID。复制、分享和模板物化继续走同一函数，避免旁路。

- [ ] **Step 6: 运行回归并提交**

```powershell
node frontend/src/views/dashboard/common/DashboardSqlEditor.date-filter.test.mjs
node frontend/src/views/dashboard/editor/ChatChartSelection.date-control.test.mjs
node frontend/src/views/chat/chat-block/ChartBlock.date-filter-v2.test.mjs
backend\.venv\Scripts\python.exe -m pytest tests/test_dashboard_chart_config_v2.py backend/tests/test_dashboard_platform_template_snapshot.py tests/test_dashboard_service.py -k "canvas or copy or template or date_filter" -q
git add -- frontend/src/views/dashboard/common/DashboardSqlEditor.vue frontend/src/views/dashboard/common/DashboardSqlEditor.date-filter.test.mjs frontend/src/views/dashboard/editor/ChatChartSelection.vue frontend/src/views/dashboard/editor/ChatChartSelection.date-control.test.mjs frontend/src/views/chat/chat-block/ChartBlock.vue frontend/src/views/chat/chat-block/ChartBlock.date-filter-v2.test.mjs backend/apps/dashboard/crud/dashboard_service.py backend/tests/test_dashboard_platform_template_snapshot.py tests/test_dashboard_service.py
git commit -m "功能：统一看板图表配置写入入口"
```

Expected: PASS；所有可保存图表均为 V2，不完整旧图表被明确拒绝。

---

### Task 6: 接入独立 API 请求与图表有限状态机

**Files:**
- Modify: `frontend/src/views/dashboard/components/sq-view/index.vue:1281`
- Modify: `frontend/src/views/dashboard/preview/SQPreviewShow.vue:624`
- Modify: `frontend/src/views/dashboard/editor/index.vue:454`
- Modify: `frontend/src/views/dashboard/preview/SQComponentWrapper.vue:652`
- Modify: `frontend/src/i18n/zh-CN.json`
- Modify: `frontend/src/i18n/zh-TW.json`
- Modify: `frontend/src/i18n/en.json`
- Modify: `frontend/src/i18n/ko-KR.json`
- Modify: `frontend/src/views/dashboard/components/sq-view/index.date-filter.test.mjs`
- Modify: `frontend/src/views/dashboard/preview/SQPreviewShow.date-filter.test.mjs`
- Modify: `frontend/src/views/dashboard/editor/index.permission-refresh.test.mjs`

**Interfaces:**
- Consumes: Task 3 后端 `date_filter` API、Task 4 请求构造器、Task 1 状态分类。
- Produces: `{date_filter, pivot}` 分离请求和请求结束必达终态的页面行为。

- [ ] **Step 1: 写请求结构、竞态和状态终结失败测试**

```javascript
assert.deepEqual(lastRequest.date_filter, {
  parameter_type: 'yyyymmdd_number',
  expression: { version: 1, mode: 'preset', preset: 'past_7_days' },
  custom_start: '2026-07-20',
  custom_end: '2026-07-26',
})
assert.deepEqual(lastRequest.pivot, { enabled: false })
assert.equal('custom_start' in lastRequest.pivot, false)
assert.equal(viewInfo.dataState, 'failed')
assert.equal(requestCount, 1)
```

同一测试先断言首次请求的 `custom_start/custom_end` 都为空、由后端持久化表达式解析为过去 7 天；收到 capability 后再点击“应用”，才产生示例中的自定义范围。另写旧请求后返回、用户新日期请求先完成的竞态测试，断言旧响应不覆盖新结果；有快照终态错误进入 `stale`，权限错误清除不可授权快照并进入 `failed`。

- [ ] **Step 2: 运行测试并确认请求仍复用 pivot**

```powershell
node frontend/src/views/dashboard/components/sq-view/index.date-filter.test.mjs
node frontend/src/views/dashboard/preview/SQPreviewShow.date-filter.test.mjs
node frontend/src/views/dashboard/editor/index.permission-refresh.test.mjs
```

Expected: FAIL，请求仍把自定义日期放在 `pivot.custom_start/custom_end`。

- [ ] **Step 3: 修改所有预览请求构造**

```typescript
const request = {
  datasource: executionDatasourceId,
  sql: viewInfo.sql,
  date_filter: buildAppliedDashboardDateFilterRequest(viewInfo),
  pivot: buildDashboardPivotRequest(viewInfo),
}
```

源数据预览只设置 `pivot: {...pivot, enabled:false}`，不得禁用或删除 `date_filter`。混合数据与外部 MCP 快照保持既有能力边界，`date_filter` 为空。

- [ ] **Step 4: 接入 `loading/ready/refreshing/stale/failed`**

首次无快照请求设为 `loading`，有快照刷新设为 `refreshing`；成功设为 `ready`；终态或重试耗尽按快照进入 `stale/failed`。所有 `finally` 分支调用 `finishDashboardChartRequest`，并断言当前请求版本后才可改状态。

为失败结果增加纯映射，不展示后端内部 reason：

```typescript
export function dashboardChartFailureMessageKey(result: DashboardRefreshResult) {
  const errorType = String(result?.error_type || '')
  if (errorType === 'dashboard_date_filter_migration_required') {
    return 'dashboard.chart_config_upgrade_required'
  }
  if (errorType === 'dashboard_date_filter_unconfigured'
    || errorType === 'dashboard_date_filter_invalid_template') {
    return 'dashboard.chart_config_invalid'
  }
  return 'dashboard.chart_refresh_failed'
}
```

四份语言文件分别增加：中文简体“图表配置待升级”“图表配置错误”，中文繁体“圖表設定待升級”“圖表設定錯誤”，英文“Chart configuration needs an upgrade”“Invalid chart configuration”，韩文“차트 구성을 업그레이드해야 합니다”“차트 구성이 올바르지 않습니다”。`SQView` 只在无快照 `failed` 时显示该文案；有快照 `stale` 继续显示图表，并使用现有刷新失败提示区域，不新增卡片或改变布局。

- [ ] **Step 5: 运行前端测试、构建并提交**

```powershell
node frontend/src/views/dashboard/components/sq-view/index.date-filter.test.mjs
node frontend/src/views/dashboard/preview/SQPreviewShow.date-filter.test.mjs
node frontend/src/views/dashboard/preview/SQPreviewShow.permission-refresh.test.mjs
node frontend/src/views/dashboard/editor/index.permission-refresh.test.mjs
Set-Location frontend
npm run build
Set-Location ..
git add -- frontend/src/views/dashboard/components/sq-view/index.vue frontend/src/views/dashboard/preview/SQPreviewShow.vue frontend/src/views/dashboard/editor/index.vue frontend/src/views/dashboard/preview/SQComponentWrapper.vue frontend/src/views/dashboard/components/sq-view/index.date-filter.test.mjs frontend/src/views/dashboard/preview/SQPreviewShow.date-filter.test.mjs frontend/src/views/dashboard/editor/index.permission-refresh.test.mjs frontend/src/i18n/zh-CN.json frontend/src/i18n/zh-TW.json frontend/src/i18n/en.json frontend/src/i18n/ko-KR.json
git commit -m "修复：统一看板图表刷新终态"
```

Expected: 测试与构建 PASS；正常 UI 模板无结构变化。

---

### Task 7: 创建迁移审计表和纯迁移服务

**Files:**
- Modify: `backend/apps/dashboard/models/dashboard_model.py`
- Create: `backend/alembic/versions/150_dashboard_date_filter_migration_audit.py`
- Create: `backend/apps/dashboard/crud/dashboard_date_filter_migration.py`
- Create: `backend/tests/test_dashboard_date_filter_migration.py`

**Interfaces:**
- Produces: `classify_chart(...)`、`plan_dashboard_migration(...)`、`apply_dashboard_migration(...)`、`rollback_dashboard_migration(...)`。
- Consumes: `MigrationManifestEntry`、`CoreDashboard.canvas_view_info`、Task 2 的解析器和 Task 3 的日期渲染器。

- [ ] **Step 1: 写分类、幂等、CAS 和回滚失败测试**

```python
def test_classification_is_explicit_and_never_uses_title():
    assert classify_chart(_complete_v1_view(), manifest=None).classification == "automatic"
    assert classify_chart(_missing_v1_view(title="近七天"), manifest=None).classification == "manual_review"
    assert classify_chart(_missing_v1_view(title="任意标题"), manifest=_approved()).classification == "approved_repair"

def test_apply_is_idempotent_and_preserves_non_target_views(session):
    first = apply_dashboard_migration(session, _plan(), operator_id="7")
    second = apply_dashboard_migration(session, _plan_from_current(), operator_id="7")
    assert first.status == "applied"
    assert second.status == "already_v2"
    assert stable_json_hash(_unlisted_view_after()) == stable_json_hash(_unlisted_view_before())

def test_cas_conflict_never_overwrites_user_edit(session):
    _edit_dashboard_after_plan(session)
    with pytest.raises(DashboardMigrationConflict, match="cas_conflict"):
        apply_dashboard_migration(session, _plan(), operator_id="7")

def test_rollback_rejects_post_migration_user_edit(session):
    audit = _applied_audit(session)
    _edit_dashboard_after_apply(session)
    with pytest.raises(DashboardMigrationConflict, match="rollback_conflict"):
        rollback_dashboard_migration(session, audit.batch_id, audit.dashboard_id, operator_id="7")
```

- [ ] **Step 2: 运行测试并确认服务和表不存在**

```powershell
backend\.venv\Scripts\python.exe -m pytest backend/tests/test_dashboard_date_filter_migration.py -q
```

Expected: FAIL，迁移服务尚未定义。

- [ ] **Step 3: 创建审计模型和 Alembic**

```python
class DashboardDateFilterMigrationAudit(SQLModel, table=True):
    __tablename__ = "core_dashboard_date_filter_migration_audit"
    __table_args__ = (
        UniqueConstraint(
            "batch_id", "dashboard_id", "chart_id",
            name="uq_dashboard_date_filter_audit_batch_chart",
        ),
        Index("idx_dashboard_date_filter_audit_tenant_status", "tenant_id", "status"),
        Index("idx_dashboard_date_filter_audit_dashboard_status", "dashboard_id", "status"),
    )
    id: str = Field(sa_column=Column(String(50), primary_key=True))
    batch_id: str = Field(sa_column=Column(String(64), nullable=False))
    tenant_id: int = Field(sa_column=Column(BigInteger, nullable=False))
    dashboard_id: str = Field(sa_column=Column(String(50), nullable=False))
    chart_id: str = Field(sa_column=Column(String(64), nullable=False))
    classification: str = Field(sa_column=Column(String(32), nullable=False))
    status: str = Field(sa_column=Column(String(32), nullable=False))
    reason: str = Field(default="", sa_column=Column(Text, nullable=False))
    target_date_filter: str = Field(sa_column=Column(Text, nullable=False))
    original_canvas: str = Field(sa_column=Column(Text, nullable=False))
    original_hash: str = Field(sa_column=Column(String(64), nullable=False))
    new_hash: str = Field(default="", sa_column=Column(String(64), nullable=False))
    validation_result: str = Field(default="{}", sa_column=Column(Text, nullable=False))
    operator_id: str = Field(sa_column=Column(String(255), nullable=False))
    created_at: int = Field(sa_column=Column(BigInteger, nullable=False))
    rolled_back_at: int | None = Field(default=None, sa_column=Column(BigInteger, nullable=True))
```

Alembic 文件使用以下完整表结构；`downgrade` 只删除审计表，不修改 `core_dashboard`：

```python
"""增加看板日期筛选迁移审计。"""

import sqlalchemy as sa
from alembic import op

revision = "150dashboarddatefilteraudit"
down_revision = "149dashboardexecutiondatasource"
branch_labels = None
depends_on = None

TABLE = "core_dashboard_date_filter_migration_audit"

def upgrade() -> None:
    op.create_table(
        TABLE,
        sa.Column("id", sa.String(50), primary_key=True),
        sa.Column("batch_id", sa.String(64), nullable=False),
        sa.Column("tenant_id", sa.BigInteger(), nullable=False),
        sa.Column("dashboard_id", sa.String(50), nullable=False),
        sa.Column("chart_id", sa.String(64), nullable=False),
        sa.Column("classification", sa.String(32), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("target_date_filter", sa.Text(), nullable=False),
        sa.Column("original_canvas", sa.Text(), nullable=False),
        sa.Column("original_hash", sa.String(64), nullable=False),
        sa.Column("new_hash", sa.String(64), nullable=False),
        sa.Column("validation_result", sa.Text(), nullable=False),
        sa.Column("operator_id", sa.String(255), nullable=False),
        sa.Column("created_at", sa.BigInteger(), nullable=False),
        sa.Column("rolled_back_at", sa.BigInteger(), nullable=True),
        sa.UniqueConstraint(
            "batch_id", "dashboard_id", "chart_id",
            name="uq_dashboard_date_filter_audit_batch_chart",
        ),
    )
    op.create_index(
        "idx_dashboard_date_filter_audit_tenant_status",
        TABLE,
        ["tenant_id", "status"],
    )
    op.create_index(
        "idx_dashboard_date_filter_audit_dashboard_status",
        TABLE,
        ["dashboard_id", "status"],
    )

def downgrade() -> None:
    op.drop_table(TABLE)
```

- [ ] **Step 4: 实现纯计划和事务写入**

```python
def apply_dashboard_migration(session: Session, plan: DashboardMigrationPlan, operator_id: str):
    current = session.exec(
        select(CoreDashboard).where(
            CoreDashboard.id == plan.dashboard_id,
            CoreDashboard.tenant_id == plan.tenant_id,
            CoreDashboard.delete_flag == 0,
        ).with_for_update()
    ).one()
    if stable_json_hash(current.canvas_view_info) != plan.original_hash:
        raise DashboardMigrationConflict("cas_conflict")
    current.canvas_view_info = plan.new_canvas
    current.update_time = int(time.time() * 1000)
    session.add_all(build_audit_rows(plan, operator_id))
    session.add(current)
    session.flush()
    verify_persisted_dashboard(session, plan)
    return MigrationApplyResult(status="applied", batch_id=plan.batch_id)
```

分类规则固定为：完整且匹配的 V1 为 `automatic`；清单精确命中且目标配置合法为 `approved_repair`；其他含 token 的非 V2 图表为 `manual_review`。一张看板一个事务；任一图表验证失败回滚整张看板。

- [ ] **Step 5: 实现条件回滚**

回滚加载同批次同看板审计记录，确认每条记录的 `new_hash` 相同且当前画布哈希等于该值后，恢复完整 `original_canvas`。不相等则记录 `rollback_conflict` 并拒绝覆盖；成功后读回核对 `original_hash`，更新 `status='rolled_back'` 和 `rolled_back_at`。

- [ ] **Step 6: 运行迁移测试、Alembic 检查并提交**

```powershell
backend\.venv\Scripts\python.exe -m pytest backend/tests/test_dashboard_date_filter_migration.py -q
Set-Location backend
.venv\Scripts\python.exe -m alembic heads
.venv\Scripts\python.exe -m alembic upgrade 150dashboarddatefilteraudit --sql > $env:TEMP\dashboard-date-filter-v2-audit.sql
Set-Location ..
git add -- backend/apps/dashboard/models/dashboard_model.py backend/alembic/versions/150_dashboard_date_filter_migration_audit.py backend/apps/dashboard/crud/dashboard_date_filter_migration.py backend/tests/test_dashboard_date_filter_migration.py
git commit -m "功能：增加看板日期迁移审计与回滚"
```

Expected: PASS；Alembic 只有一个 head，生成 SQL 包含审计表、唯一约束和索引。

---

### Task 8: 实现通用迁移 CLI 和当前工作空间清单

**Files:**
- Create: `tools/dashboard_date_filter_v2_migration.py`
- Create: `tools/dashboard_date_filter_v2_manifests/2026-07-29-workspace-7482727237662281728.json`
- Modify: `backend/tests/test_dashboard_date_filter_migration.py`

**Interfaces:**
- Consumes: Task 7 迁移服务、清单 JSON、核心系统数据库连接配置。
- Produces: `scan`、`apply`、`rollback`、`count-v1` 四类命令及机器可读 JSON 报告。

- [ ] **Step 1: 创建精确试点清单**

```json
{
  "manifestVersion": 1,
  "tenantId": 7482727237662281728,
  "batchName": "dashboard-date-filter-v2-pilot-20260729",
  "entries": [
    {
      "dashboardId": "1752a05a80724b379438838bee516a46",
      "chartId": "2197205356986408960",
      "classification": "approved_repair",
      "parameterType": "yyyymmdd_number",
      "expression": {"version": 1, "mode": "preset", "preset": "past_7_days"},
      "reason": "已确认 SQL 使用成对 YYYYMMDD token，但关闭透视后旧日期配置缺失"
    },
    {
      "dashboardId": "1752a05a80724b379438838bee516a46",
      "chartId": "2197218114511478784",
      "classification": "approved_repair",
      "parameterType": "yyyymmdd_number",
      "expression": {"version": 1, "mode": "preset", "preset": "past_7_days"},
      "reason": "已确认 SQL 使用成对 YYYYMMDD token，但旧配置缺少日期参数类型和表达式"
    }
  ]
}
```

- [ ] **Step 2: 写 CLI 默认预演和范围保护测试**

```python
def test_cli_defaults_to_dry_run_and_requires_exact_tenant(monkeypatch):
    result = cli.run(["scan", "--manifest", str(MANIFEST)])
    assert result["applied"] is False
    assert result["tenant_id"] == 7482727237662281728
    assert result["planned_chart_count"] == 2

def test_apply_requires_explicit_batch_id():
    with pytest.raises(SystemExit):
        cli.parse_args(["apply", "--manifest", str(MANIFEST)])
```

- [ ] **Step 3: 实现命令行入口**

```python
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    scan = subparsers.add_parser("scan")
    scan.add_argument("--tenant-id", type=int)
    scan.add_argument("--manifest", type=Path)
    apply = subparsers.add_parser("apply")
    apply.add_argument("--manifest", type=Path, required=True)
    apply.add_argument("--batch-id", required=True)
    rollback = subparsers.add_parser("rollback")
    rollback.add_argument("--batch-id", required=True)
    rollback.add_argument("--dashboard-id")
    count = subparsers.add_parser("count-v1")
    count.add_argument("--tenant-id", type=int)
    return parser
```

`scan` 输出每图版本、token、旧配置、分类、目标配置和拒绝原因；`apply` 只写 `automatic/approved_repair`；`manual_review` 必须保持不变。所有命令输出 `batch_id`、计数、哈希、CAS 冲突和验证结果，不输出完整 SQL、凭据或业务结果。

- [ ] **Step 4: 运行测试和试点预演**

```powershell
backend\.venv\Scripts\python.exe -m pytest backend/tests/test_dashboard_date_filter_migration.py -q
backend\.venv\Scripts\python.exe tools/dashboard_date_filter_v2_migration.py scan --manifest tools/dashboard_date_filter_v2_manifests/2026-07-29-workspace-7482727237662281728.json
```

Expected: `applied=false`、`planned_dashboard_count=1`、`planned_chart_count=2`、`approved_repair=2`、`manual_review=0`；不产生数据库更新或审计记录。

- [ ] **Step 5: 提交迁移工具，暂不执行写库**

```powershell
git add -- tools/dashboard_date_filter_v2_migration.py tools/dashboard_date_filter_v2_manifests/2026-07-29-workspace-7482727237662281728.json backend/tests/test_dashboard_date_filter_migration.py
git commit -m "工具：增加看板日期 V2 显式迁移"
```

Expected: 提交只包含工具、清单和测试；数据库仍未变化。

---

### Task 9: 执行试点迁移并做页面验收

**Files:**
- Database write: `public.core_dashboard.canvas_view_info`
- Database write: `public.core_dashboard_date_filter_migration_audit`
- Runtime artifact: `.codex-runtime/dashboard-date-filter-v2-reports/<batch-id>.json`

**Interfaces:**
- Consumes: 已评审并部署的 Tasks 1-8、试点清单。
- Produces: 两张 V2 图表、审计记录、只读执行验证和页面验收证据。

- [ ] **Step 1: 执行前置备份和最终预演**

```powershell
.\tools\postgres-backup-local.ps1
backend\.venv\Scripts\python.exe tools/dashboard_date_filter_v2_migration.py scan --manifest tools/dashboard_date_filter_v2_manifests/2026-07-29-workspace-7482727237662281728.json
```

Expected: PostgreSQL 备份成功；预演仍为 1 个看板、2 个 `approved_repair`，原始哈希与评审记录一致。若不一致立即停止，不执行下一步。

- [ ] **Step 2: 显式应用单看板迁移**

```powershell
backend\.venv\Scripts\python.exe tools/dashboard_date_filter_v2_migration.py apply --manifest tools/dashboard_date_filter_v2_manifests/2026-07-29-workspace-7482727237662281728.json --batch-id dashboard-date-filter-v2-pilot-20260729-01
```

Expected: `applied_dashboard_count=1`、`applied_chart_count=2`、`cas_conflict=0`、`validation_failed=0`；审计记录保存完整原始画布和前后哈希。

- [ ] **Step 3: 只读核对写后结构和 SQL**

```powershell
backend\.venv\Scripts\python.exe tools/dashboard_date_filter_v2_migration.py scan --manifest tools/dashboard_date_filter_v2_manifests/2026-07-29-workspace-7482727237662281728.json
```

Expected: 两图均为 `configVersion=2`；`dateFilter` 完整；图表 `2197205356986408960` 仍为 `pivot.enabled=false`，图表 `2197218114511478784` 的透视字段逐项保持；非目标图表哈希不变；V1 清单不再包含这两图。

通过现有 `/dashboard/sql_preview` 权限链分别验证默认过去 7 天与一个自定义范围，断言最终 SQL 无 token、日期边界正确、返回字段不变、无权限绕过。

- [ ] **Step 4: 浏览器验收且不改正常表现**

1. 打开看板 `test2`，确认两张图不再永久显示“数据加载中”。
2. 确认 `近七天各渠道累计付费金额` 仍显示透视关闭，但日期入口可用。
3. 确认 `近七天渠道新增用户趋势` 的透视、分组、时间粒度和图表结果保持。
4. 修改日期但不点“应用”时不请求；点“应用”后只刷新当前图表。
5. 在无快照配置错误 fixture 下显示明确失败；有快照 fixture 下显示旧数据和刷新失败状态。
6. 在桌面与移动宽度检查标题、日期控件和图表不重叠；保存前后 DOM 结构截图用于视觉回归。

- [ ] **Step 5: 演练条件回滚后重新应用**

在测试环境使用同批次执行：

```powershell
backend\.venv\Scripts\python.exe tools/dashboard_date_filter_v2_migration.py rollback --batch-id dashboard-date-filter-v2-pilot-20260729-01 --dashboard-id 1752a05a80724b379438838bee516a46
```

Expected: 恢复原始哈希并记录 `rolled_back`。随后重新使用新批次 ID 应用并重复 Step 3 验证。若回滚前人为编辑画布，命令必须返回 `rollback_conflict` 且不覆盖编辑。

- [ ] **Step 6: 记录试点结果，不提交数据库快照**

将脱敏计数、耗时、哈希、页面截图路径和回滚结果写入 `.codex-runtime/dashboard-date-filter-v2-reports/`。该目录不暂存、不提交；Git 不产生代码提交。

---

### Task 10: 增加灰度门禁、可观测性和 V1 清理步骤

**Files:**
- Create: `docs/dashboard_date_filter_v2_rollout.md`
- Modify: `backend/apps/dashboard/crud/dashboard_service.py`
- Modify: `backend/apps/dashboard/crud/dashboard_date_filter_legacy.py`
- Modify: `frontend/src/views/dashboard/utils/dashboardPermissionRefresh.ts`
- Modify: `tests/test_dashboard_chart_config_v2.py`
- Modify: `backend/tests/test_dashboard_date_filter_migration.py`

**Interfaces:**
- Consumes: 结构化 `error_type`、迁移审计、V1 数量统计。
- Produces: 可执行灰度检查清单、低基数指标、V1 关闭和删除门禁。

- [ ] **Step 1: 写指标维度和删除门禁失败测试**

```python
def test_dashboard_metric_labels_are_low_cardinality():
    labels = dashboard_metric_labels(
        status="failed",
        error_type="dashboard_date_filter_migration_required",
        config_version="v1",
    )
    assert labels == {
        "status": "failed",
        "error_type": "dashboard_date_filter_migration_required",
        "config_version": "v1",
    }
    assert "tenant_id" not in labels
    assert "dashboard_id" not in labels
    assert "chart_id" not in labels

def test_v1_cleanup_gate_requires_two_seven_day_windows():
    assert can_delete_v1_reader(v1_zero_days=7, reader_disabled_days=6) is False
    assert can_delete_v1_reader(v1_zero_days=14, reader_disabled_days=7) is True
```

- [ ] **Step 2: 实现结构化观测字段**

后端日志字段固定为 `tenant_id/user_id/dashboard_id/chart_id/datasource_id/config_version/error_type/request_stage/elapsed_ms/sql_fingerprint`；ID 只进入日志，不进入时序指标标签。前端记录请求结束仍处于 `loading/refreshing` 的状态异常，并记录终态错误发生重试的程序错误事件。

指标固定为：配置版本数量、请求成功率、错误类型、执行耗时、重试次数、重试耗尽、迁移分类/状态、CAS 冲突和回滚状态。不得把 SQL、标题、租户 ID、看板 ID 或图表 ID 作为指标 label。

- [ ] **Step 3: 编写按租户灰度运行手册**

文档必须包含以下可直接执行的门禁：

1. 每租户先 `scan`，人工审核 `approved_repair/manual_review`，再使用唯一批次 ID `apply`。
2. 任一非目标字段变化、CAS 冲突、写后验证失败或终态错误自动重试，立即暂停当前租户批次。
3. 每批核对加载成功率、错误类型、P95 执行耗时、V1 数量和回滚可用性。
4. V1 数量未归零时禁止关闭 `DASHBOARD_DATE_FILTER_V1_READ_ENABLED`。
5. V1 归零并连续至少 7 个自然日后，发布开关关闭；关闭后连续至少 7 个自然日无回归，再单独提交删除 V1 读取器、开关、旧测试和旧 `pivot` 日期字段。

- [ ] **Step 4: 运行回归并提交观测与文档**

```powershell
backend\.venv\Scripts\python.exe -m pytest tests/test_dashboard_chart_config_v2.py backend/tests/test_dashboard_date_filter_migration.py tests/test_dashboard_service.py -q
node frontend/src/views/dashboard/utils/dashboardPermissionRefresh.test.mjs
git add -- docs/dashboard_date_filter_v2_rollout.md backend/apps/dashboard/crud/dashboard_service.py backend/apps/dashboard/crud/dashboard_date_filter_legacy.py frontend/src/views/dashboard/utils/dashboardPermissionRefresh.ts tests/test_dashboard_chart_config_v2.py backend/tests/test_dashboard_date_filter_migration.py
git commit -m "运维：增加看板日期 V2 灰度与清理门禁"
```

Expected: PASS；运行手册明确每批暂停与回滚条件。

- [ ] **Step 5: 在满足观察期后单独删除 V1 兼容代码**

仅当 `count-v1` 连续至少 14 天为 0，且读取器关闭连续至少 7 天无回归时执行：删除 `dashboard_date_filter_legacy.py`、配置开关、V1 分支和专用测试；保留迁移审计表与只读审计记录。该清理必须单独 PR、单独回归、单独回滚，不与任何租户迁移同批发布。

---

## Final Verification

- [ ] 运行后端相关测试：

```powershell
backend\.venv\Scripts\python.exe -m pytest tests/test_dashboard_chart_config_v2.py tests/test_dashboard_date_filter.py tests/test_dashboard_service.py backend/tests/test_dashboard_permission_cache.py backend/tests/test_dashboard_execution_datasource.py backend/tests/test_dashboard_platform_template_snapshot.py backend/tests/test_dashboard_date_filter_migration.py -q
```

- [ ] 运行前端相关测试与构建：

```powershell
node frontend/src/views/dashboard/utils/dashboardChartConfig.test.mjs
node frontend/src/views/dashboard/utils/dashboardPermissionRefresh.test.mjs
node frontend/src/views/dashboard/common/DashboardSqlEditor.date-filter.test.mjs
node frontend/src/views/dashboard/editor/ChatChartSelection.date-control.test.mjs
node frontend/src/views/chat/chat-block/ChartBlock.date-filter-v2.test.mjs
node frontend/src/views/dashboard/components/sq-view/index.date-filter.test.mjs
node frontend/src/views/dashboard/preview/SQPreviewShow.date-filter.test.mjs
node frontend/src/views/dashboard/preview/SQPreviewShow.permission-refresh.test.mjs
node frontend/src/views/dashboard/editor/index.permission-refresh.test.mjs
Set-Location frontend
npm run build
Set-Location ..
```

- [ ] 运行 `git diff --check`，确认无空白错误。
- [ ] 运行 `git status --short`，确认没有暂存无关 SQL 分析文件、日志、数据库备份、迁移报告或构建产物。
- [ ] 核对正常前端 DOM 与截图，确认日期入口、面板、透视控件和卡片布局无变化。
- [ ] 核对终态错误只请求一次，瞬态错误最多重试 3 次，请求结束后无图表停留在 `loading/refreshing`。
- [ ] 核对两个试点图表迁移后日期边界、权限、返回字段、透视配置和结果语义；非目标图表哈希不变。
- [ ] 核对审计记录包含完整恢复快照、前后哈希、分类、执行人、验证结果和回滚状态。
- [ ] 在测试环境完成一次成功回滚和一次回滚冲突拒绝演练。
- [ ] 确认 V1 读取器删除前满足两个观察窗口，且清理是独立发布。
