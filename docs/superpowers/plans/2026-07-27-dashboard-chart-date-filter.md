# 看板图表独立日期筛选 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为“我的看板”和工作空间内“推荐看板”的普通 SQL 图表增加逐图表日期选择与“应用”执行能力，同时可靠隐藏读取 `event_realtime` 的图表。

**Architecture:** 复用现有 `pivot`、`/dashboard/sql_preview`、SQL 权限校验、缓存和刷新队列。新增独立后端日期模板模块负责词法识别、默认日期、模板渲染和真实表解析；新增前端纯状态模块负责草稿/生效日期，现有 `SQView` 只负责交互接线。第一阶段不迁移任何现有看板 SQL 或配置。

**Tech Stack:** Python 3.11、FastAPI、Pydantic、SQLGlot、Pytest、Vue 3、TypeScript、Element Plus Secondary、Node `assert` 测试、Vite。

## Global Constraints

- 只覆盖“我的看板”和工作空间内“推荐看板”的普通 SQL 图表。
- 每张图表独立维护日期状态；不得联动刷新其他图表。
- 默认范围为昨天减 13 天至昨天，共 14 个完整自然日，不包含今天。
- 只有明确配置 `pivot.time_field`、合法日期参数类型和完整模板参数的图表才显示日期操作区。
- 后端解析到真实物理表 `event_realtime` 时隐藏日期操作区；禁止前端字符串判断。
- SQL 注释、字符串常量和同名 CTE 不得造成 `event_realtime` 误判。
- 不自动猜测时间字段、参数类型或 SQL 日期谓词。
- 日期选择只在当前页面会话有效，不写 Pinia 持久化、浏览器存储或看板保存接口。
- 本计划不修改现有看板 SQL、`canvas_view_info`、业务数据，不创建数据库迁移。
- 混合数据图表、外部 MCP 快照、ROI 看板、智能问答图表和 SaaS 平台模板编辑页不在范围内。
- 后端最终渲染 SQL 必须继续经过只读、数据源、表、字段和行权限校验。
- 所有提交信息使用中文；每次只暂存当前任务文件。

---

## File Map

- `backend/apps/dashboard/crud/dashboard_date_filter.py`：日期模板词法扫描、默认日期、能力判定、模板渲染和真实表解析，保持纯函数边界。
- `backend/apps/dashboard/models/dashboard_model.py`：扩展 `DashboardPivotRequest.date_parameter_type` 请求契约。
- `backend/apps/dashboard/crud/dashboard_service.py`：将模板准备结果接入权限审计、缓存、SQL 执行和看板临时响应，不保存能力信息。
- `backend/common/core/config.py`：增加可配置业务时区 `DASHBOARD_BUSINESS_TIMEZONE`。
- `frontend/src/views/dashboard/utils/dashboardDateFilter.ts`：日期能力、默认范围、草稿/生效状态和请求 payload 纯函数。
- `frontend/src/views/dashboard/components/sq-view/index.vue`：渲染日期范围选择器和“应用”按钮，复用现有 `refreshData`。
- `frontend/src/views/dashboard/preview/SQPreviewShow.vue`：首次加载默认日期、缓存优先和并发刷新接线。
- `frontend/src/views/dashboard/common/DashboardSqlEditor.vue`：显式选择并持久化日期参数类型，预览模板 SQL。
- `frontend/src/i18n/{zh-CN,zh-TW,en,ko-KR}.json`：日期筛选文案。

---

### Task 1: 后端日期模板核心

**Files:**
- Create: `backend/apps/dashboard/crud/dashboard_date_filter.py`
- Create: `tests/test_dashboard_date_filter.py`
- Modify: `backend/common/core/config.py:125`

**Interfaces:**
- Produces: `DashboardDateFilterPreparation`、`default_dashboard_date_range()`、`prepare_dashboard_date_filter()`。
- Consumes: `parse_sql_statements()`、`extract_physical_tables()` from `backend/apps/datasource/crud/sql_permission.py`。

- [ ] **Step 1: 写失败测试覆盖默认日期、模板类型和实时表解析**

```python
from datetime import date

from apps.dashboard.crud.dashboard_date_filter import prepare_dashboard_date_filter


def test_default_range_is_fourteen_complete_days():
    result = prepare_dashboard_date_filter(
        "select dt, amount from orders where dt between {{dashboard_start_yyyymmdd}} and {{dashboard_end_yyyymmdd}}",
        ds_type="mysql",
        pivot={"time_field": "dt", "date_parameter_type": "yyyymmdd_number"},
        today=date(2026, 7, 27),
    )
    assert result.start == "2026-07-13"
    assert result.end == "2026-07-26"
    assert "20260713" in result.sql and "20260726" in result.sql
    assert result.capability["status"] == "available"


def test_realtime_physical_table_hides_filter_but_cte_and_comments_do_not():
    realtime = prepare_dashboard_date_filter(
        "select dt from event_realtime where dt={{dashboard_start_yyyymmdd}}",
        ds_type="mysql",
        pivot={"time_field": "dt", "date_parameter_type": "yyyymmdd_number"},
        today=date(2026, 7, 27),
    )
    assert realtime.capability["status"] == "realtime"

    historical = prepare_dashboard_date_filter(
        "with event_realtime as (select dt from event) select dt from event_realtime "
        "where dt between {{dashboard_start_yyyymmdd}} and {{dashboard_end_yyyymmdd}} "
        "and 'event_realtime'='event_realtime' /* event_realtime */",
        ds_type="mysql",
        pivot={"time_field": "dt", "date_parameter_type": "yyyymmdd_number"},
        today=date(2026, 7, 27),
    )
    assert historical.capability["status"] == "available"
    assert historical.physical_tables == {"event"}
```

- [ ] **Step 2: 运行测试并确认失败**

Run: `backend\.venv\Scripts\python.exe -m pytest tests/test_dashboard_date_filter.py -q`

Expected: FAIL，提示 `apps.dashboard.crud.dashboard_date_filter` 不存在。

- [ ] **Step 3: 实现最小纯函数模块**

```python
DateParameterType = Literal["date", "yyyymmdd_number", "yyyymmdd_text", "timestamp"]


@dataclass(frozen=True)
class DashboardDateFilterPreparation:
    sql: str
    start: str | None
    end: str | None
    physical_tables: set[str]
    capability: dict[str, str]


def default_dashboard_date_range(*, today: date) -> tuple[date, date]:
    end = today - timedelta(days=1)
    return end - timedelta(days=13), end


def prepare_dashboard_date_filter(
    sql: str,
    *,
    ds_type: str | None,
    pivot: Any | None,
    today: date | None = None,
) -> DashboardDateFilterPreparation:
    """只处理受控模板；不得猜测字段或改写其他 SQL 条件。"""
```

实现要求：

- 用小型词法扫描器区分普通 SQL、单/双引号、反引号、方括号标识符、`--`/`#` 行注释和 `/* */` 块注释。
- 只替换普通 SQL 状态下的固定 token。
- 参数家族必须完整且与 `date_parameter_type` 一致。
- `yyyymmdd_number` 渲染无引号 8 位数字；`yyyymmdd_text` 渲染方言安全字符串字面量。
- `timestamp` 使用开始日零点和结束日下一天零点。
- 先渲染安全字面量，再调用 `parse_sql_statements` 和 `extract_physical_tables`。
- 任一物理表规范化后等于 `event_realtime`，返回 `realtime` 且不应用日期模板。
- 无时间字段、无完整参数、混用家族或解析失败分别返回 `unconfigured`，并提供稳定 `reason`。
- 从 `ZoneInfo(settings.DASHBOARD_BUSINESS_TIMEZONE)` 获取默认业务日期；测试必须传入 `today`，不依赖机器时钟。
- `DASHBOARD_BUSINESS_TIMEZONE` 无法被 `ZoneInfo` 解析时启动配置校验失败，不回退到机器本地时区。

在 `Settings` 中增加：

```python
DASHBOARD_BUSINESS_TIMEZONE: str = "Asia/Shanghai"
```

- [ ] **Step 4: 补齐边界测试并运行**

增加测试：日期字段、数字/文本 `YYYYMMDD`、时间戳左闭右开、开始晚于结束、今天/未来日期、缺失参数、混用参数、token 位于注释/字符串、schema/引号表名和 SQL 解析失败。

Run: `backend\.venv\Scripts\python.exe -m pytest tests/test_dashboard_date_filter.py -q`

Expected: PASS，全部日期模板测试通过。

- [ ] **Step 5: 提交**

```powershell
git add -- backend/apps/dashboard/crud/dashboard_date_filter.py backend/common/core/config.py tests/test_dashboard_date_filter.py
git commit -m "功能：增加看板日期模板解析"
```

---

### Task 2: 接入 SQL 预览、权限和缓存

**Files:**
- Modify: `backend/apps/dashboard/models/dashboard_model.py:406`
- Modify: `backend/apps/dashboard/crud/dashboard_service.py:2088,2257,2656,5080`
- Modify: `tests/test_dashboard_service.py`
- Modify: `backend/tests/test_dashboard_permission_cache.py`

**Interfaces:**
- Consumes: `prepare_dashboard_date_filter()` from Task 1。
- Produces: `DashboardPivotRequest.date_parameter_type` 和 `sql_preview` 响应中的 `date_filter_capability`。

- [ ] **Step 1: 写失败测试证明模板在权限校验前渲染**

```python
def test_dashboard_preview_renders_date_template_before_permission_and_execution(monkeypatch):
    engine = _engine_with_dashboard_permission_tables()
    current_user = SimpleNamespace(id=2, isAdmin=False, tenant_id=1)
    exec_calls = []
    monkeypatch.setattr(
        query_executor,
        "_unsafe_exec_sql_after_validation",
        lambda ds, sql, origin_column=False: exec_calls.append(sql)
        or {"data": [{"order_day": "2026-05-01", "amount": 99}], "fields": ["order_day", "amount"]},
    )
    with Session(engine) as session:
        _insert_dashboard_permission_fixture(session)
        session.commit()
        result = dashboard_service.preview_sql(
            session,
            current_user,
            DashboardSqlPreview(
                datasource=1,
                sql=(
                    "select order_id as order_day, amount from orders "
                    "where order_id between {{dashboard_start_yyyymmdd}} and {{dashboard_end_yyyymmdd}}"
                ),
                pivot=DashboardPivotRequest(
                    enabled=True,
                    time_field="order_day",
                    metric_field="amount",
                    date_parameter_type="yyyymmdd_number",
                    range="custom",
                    custom_start="2026-05-01",
                    custom_end="2026-05-31",
                ),
            ),
        )
    assert result["date_filter_capability"]["status"] == "available"
    assert len(exec_calls) == 1
    assert "20260501" in exec_calls[0] and "20260531" in exec_calls[0]
    assert "{{dashboard_" not in exec_calls[0]


def test_dashboard_preview_rejects_custom_range_for_event_realtime(monkeypatch):
    prepared = DashboardDateFilterPreparation(
        sql="select dt from event_realtime",
        start=None,
        end=None,
        physical_tables={"event_realtime"},
        capability={"status": "realtime", "reason": "realtime_table"},
    )
    monkeypatch.setattr(dashboard_service, "prepare_dashboard_date_filter", lambda *args, **kwargs: prepared)
    monkeypatch.setattr(
        dashboard_service,
        "_execute_dashboard_chart_sql",
        lambda *args, **kwargs: pytest.fail("实时图表不得应用自定义日期"),
    )
    result = dashboard_service.preview_sql(
        session=SimpleNamespace(get=lambda *_: SimpleNamespace(id=1, type="mysql")),
        current_user=SimpleNamespace(id=2, isAdmin=False, tenant_id=1),
        request=DashboardSqlPreview(
            datasource=1,
            sql="select dt from event_realtime",
            pivot=DashboardPivotRequest(
                time_field="dt",
                date_parameter_type="yyyymmdd_number",
                range="custom",
                custom_start="2026-05-01",
                custom_end="2026-05-31",
            ),
        ),
    )
    assert result["status"] == "failed"
    assert result["error_type"] == "dashboard_date_filter_realtime"
```

- [ ] **Step 2: 运行目标测试并确认失败**

Run: `backend\.venv\Scripts\python.exe -m pytest tests/test_dashboard_service.py -k "date_template or event_realtime" -q`

Expected: FAIL，响应缺少能力信息或执行 SQL 仍包含模板 token。

- [ ] **Step 3: 扩展请求模型并集中准备查询**

在 `DashboardPivotRequest` 增加：

```python
date_parameter_type: Literal[
    "date", "yyyymmdd_number", "yyyymmdd_text", "timestamp"
] | None = None
```

在 `dashboard_service.py` 增加内部结构，确保一次请求只准备一次：

```python
@dataclass(frozen=True)
class PreparedDashboardChartQuery:
    source_sql: str
    pivot: Any | None
    date_filter_capability: dict[str, Any]


def _prepare_dashboard_chart_query(datasource, sql, pivot) -> PreparedDashboardChartQuery:
    prepared = prepare_dashboard_date_filter(sql, ds_type=datasource.type, pivot=pivot)
    return PreparedDashboardChartQuery(prepared.sql, pivot, prepared.capability)
```

接线要求：

- `preview_sql` 在生成权限审计、缓存键和执行请求前准备 SQL。
- 权限审计和 `_execute_dashboard_chart_sql` 接收同一份已渲染 `source_sql`。
- 透视外层 SQL仍在模板渲染之后构建。
- 用户显式传入 custom 日期而能力为 `realtime` 时 fail closed；普通看板加载实时图表仍执行原 SQL。
- 能力 `unconfigured` 且 SQL 含活动模板 token 时拒绝执行；完全没有模板的旧图表继续按原 SQL 执行但隐藏控件。
- 成功和失败响应都附加 `date_filter_capability`，不得把 SQL 模板或敏感权限详情暴露给普通用户。

- [ ] **Step 4: 让缓存键使用实际日期**

修改 `_dashboard_sql_preview_cache_key`，传入已渲染 `source_sql` 和规范化 pivot；断言跨天默认日期、不同 custom 日期、不同参数类型生成不同 fingerprint，同一条件保持相同 fingerprint。

Run: `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_dashboard_permission_cache.py tests/test_dashboard_service.py -k "cache or date_template or event_realtime" -q`

Expected: PASS。

- [ ] **Step 5: 提交**

```powershell
git add -- backend/apps/dashboard/models/dashboard_model.py backend/apps/dashboard/crud/dashboard_service.py tests/test_dashboard_service.py backend/tests/test_dashboard_permission_cache.py
git commit -m "功能：接入看板日期参数执行"
```

---

### Task 3: 看板响应临时能力标记

**Files:**
- Modify: `backend/apps/dashboard/crud/dashboard_service.py:3750`
- Modify: `tests/test_dashboard_service.py`

**Interfaces:**
- Consumes: `_prepare_dashboard_chart_query()` from Task 2。
- Produces: `_dashboard_chart_date_capability(session, current_user, datasource_id, item) -> dict[str, Any]` 和每个 `canvas_view_info` 项的临时 `dateFilterCapability`，不写回数据库。

- [ ] **Step 1: 写失败测试覆盖我的看板、推荐看板和无写入**

```python
def test_dashboard_payload_adds_transient_date_capability_without_persisting(session, monkeypatch):
    original = {
        "available": {"id": "available", "sql": "select dt from orders", "pivot": {"time_field": "dt"}},
        "realtime": {"id": "realtime", "sql": "select dt from event_realtime", "pivot": {"time_field": "dt"}},
        "plain": {"id": "plain", "sql": "select amount from orders", "pivot": {}},
    }
    record = CoreDashboard(
        id="dashboard-date-capability",
        tenant_id=1,
        name="日期能力测试",
        pid="root",
        node_type="leaf",
        datasource=1,
        component_data="[]",
        canvas_style_data="{}",
        canvas_view_info=orjson.dumps(original).decode(),
    )
    session.add(record)
    session.commit()
    monkeypatch.setattr(
        dashboard_service,
        "_dashboard_chart_date_capability",
        lambda _session, _user, _ds, item: {
            "status": "realtime" if item["id"] == "realtime" else (
                "available" if item["id"] == "available" else "unconfigured"
            )
        },
    )
    payload = dashboard_service._dashboard_payload(
        session,
        SimpleNamespace(id=2, isAdmin=False, tenant_id=1),
        record,
        default_context=True,
        include_data=False,
    )
    response_views = orjson.loads(payload["canvas_view_info"])
    assert response_views["available"]["dateFilterCapability"]["status"] == "available"
    assert response_views["realtime"]["dateFilterCapability"]["status"] == "realtime"
    assert response_views["plain"]["dateFilterCapability"]["status"] == "unconfigured"
    session.expire_all()
    assert "dateFilterCapability" not in session.get(CoreDashboard, record.id).canvas_view_info
```

- [ ] **Step 2: 运行并确认失败**

Run: `backend\.venv\Scripts\python.exe -m pytest tests/test_dashboard_service.py -k "transient_date_capability" -q`

Expected: FAIL，响应中尚无临时能力。

- [ ] **Step 3: 在 `_dashboard_payload` 的解析副本中注入能力**

响应字段固定为：

```python
{
    "status": "available",
    "reason": "",
    "parameterType": "yyyymmdd_number",
    "defaultStart": "2026-07-13",
    "defaultEnd": "2026-07-26",
    "maxEnd": "2026-07-26",
}
```

实现要求：

- 仅普通非平台模板、非外部 MCP 图表参与。
- 在 `include_data=False` 的权限审计前也生成能力，保证缓存快照页面能决定是否展示控件。
- 权限失败覆盖为 `forbidden`；混合/MCP覆盖为 `unsupported`。
- 字段名使用前端约定的 `dateFilterCapability`；只写 `canvas_view_obj` 响应副本。
- 不调用 `session.add/commit/flush`，不修改 `record.canvas_view_info`。

- [ ] **Step 4: 运行看板服务回归**

Run: `backend\.venv\Scripts\python.exe -m pytest tests/test_dashboard_service.py backend/tests/test_dashboard_permission_cache.py -q`

Expected: PASS。

- [ ] **Step 5: 提交**

```powershell
git add -- backend/apps/dashboard/crud/dashboard_service.py tests/test_dashboard_service.py
git commit -m "功能：返回图表日期筛选能力"
```

---

### Task 4: SQL 编辑器显式配置参数类型

**Files:**
- Modify: `frontend/src/views/dashboard/common/DashboardSqlEditor.vue:200,2950,2980,4196,5429`
- Create: `frontend/src/views/dashboard/common/DashboardSqlEditor.date-filter.test.mjs`
- Modify: `frontend/src/i18n/zh-CN.json`
- Modify: `frontend/src/i18n/zh-TW.json`
- Modify: `frontend/src/i18n/en.json`
- Modify: `frontend/src/i18n/ko-KR.json`

**Interfaces:**
- Produces: 持久化 `pivot.date_parameter_type`；预览请求复用 `pivot.custom_start/custom_end`。

- [ ] **Step 1: 写失败的源码契约测试**

```javascript
assert.match(source, /pivotDateParameterType/)
assert.match(source, /date_parameter_type:\s*form\.pivotDateParameterType/)
assert.match(source, /dashboard_start_yyyymmdd/)
assert.match(source, /validateBeforeApply[\s\S]*date_parameter_type/)
```

- [ ] **Step 2: 运行并确认失败**

Run from `frontend`: `node src/views/dashboard/common/DashboardSqlEditor.date-filter.test.mjs`

Expected: FAIL，编辑器尚无日期参数类型。

- [ ] **Step 3: 增加显式参数类型配置与校验**

```typescript
type DashboardDateParameterType = '' | 'date' | 'yyyymmdd_number' | 'yyyymmdd_text' | 'timestamp'

const form = reactive({
  // existing fields...
  pivotDateParameterType: '' as DashboardDateParameterType,
})
```

实现要求：

- 在时间字段设置区增加参数类型下拉菜单，而不是自动判断字段类型。
- 恢复图表时读取 `pivot.date_parameter_type`；保存/应用时写回。
- SQL 包含受控日期 token 且参数类型为空或不匹配时，预览和应用均显示明确校验错误。
- 不自动把旧 SQL 改成模板，不自动选择类型。
- 编辑器预览模板 SQL 时使用默认近 14 天；自定义范围仍使用现有 custom 字段。
- 四种语言补齐标签、选项和错误文案。

- [ ] **Step 4: 运行编辑器测试与构建**

Run from `frontend`:

```powershell
node src/views/dashboard/common/DashboardSqlEditor.date-filter.test.mjs
node src/views/dashboard/common/DashboardSqlEditor.builder-persistence.test.mjs
npm run build
```

Expected: 三条命令均退出码 0。

- [ ] **Step 5: 提交**

```powershell
git add -- frontend/src/views/dashboard/common/DashboardSqlEditor.vue frontend/src/views/dashboard/common/DashboardSqlEditor.date-filter.test.mjs frontend/src/i18n/zh-CN.json frontend/src/i18n/zh-TW.json frontend/src/i18n/en.json frontend/src/i18n/ko-KR.json
git commit -m "功能：配置图表日期参数类型"
```

---

### Task 5: 前端逐图表日期状态模块

**Files:**
- Create: `frontend/src/views/dashboard/utils/dashboardDateFilter.ts`
- Create: `frontend/src/views/dashboard/utils/dashboardDateFilter.test.mjs`

**Interfaces:**
- Produces: `createDashboardDateFilterState()`、`canShowDashboardDateFilter()`、`buildDashboardDatePivot()`、`commitDashboardDateRange()`。

- [ ] **Step 1: 写失败测试定义状态转换**

```javascript
import {
  canShowDashboardDateFilter,
  defaultDashboardDateRange,
  isDashboardDateApplyDisabled,
} from './dashboardDateFilter.ts'

assert.deepEqual(defaultDashboardDateRange('2026-07-27'), ['2026-07-13', '2026-07-26'])
assert.equal(canShowDashboardDateFilter({ status: 'available' }), true)
assert.equal(canShowDashboardDateFilter({ status: 'realtime' }), false)
assert.equal(isDashboardDateApplyDisabled(state), true)
```

- [ ] **Step 2: 运行并确认失败**

Run from `frontend`: `node --experimental-strip-types src/views/dashboard/utils/dashboardDateFilter.test.mjs`

Expected: FAIL，工具模块不存在。

- [ ] **Step 3: 实现纯状态接口**

```typescript
export type DashboardDateRange = [string, string]
export type DashboardDateCapabilityStatus =
  | 'available' | 'realtime' | 'unconfigured' | 'unsupported' | 'forbidden'

export type DashboardDateFilterState = {
  draftRange: DashboardDateRange
  appliedRange: DashboardDateRange
  pendingRange: DashboardDateRange | null
  applying: boolean
  applyError: string
}
```

实现要求：

- 使用自然日字符串运算，不调用 `toISOString()`。
- 默认日期优先使用后端 capability 的 `defaultStart/defaultEnd`；本地函数只作为显示初始化的确定性回退。
- `buildDashboardDatePivot(viewInfo, range)` 必须复制对象，不直接修改持久化 `viewInfo.pivot`。
- 禁用规则覆盖空值、格式错误、开始晚于结束、结束大于后端 `maxEnd`、与已应用范围相同和 applying。
- 成功才提交 `appliedRange`；失败只清理 pending/applying 并保留 draft。

- [ ] **Step 4: 运行纯状态测试**

Run from `frontend`: `node --experimental-strip-types src/views/dashboard/utils/dashboardDateFilter.test.mjs`

Expected: PASS。

- [ ] **Step 5: 提交**

```powershell
git add -- frontend/src/views/dashboard/utils/dashboardDateFilter.ts frontend/src/views/dashboard/utils/dashboardDateFilter.test.mjs
git commit -m "功能：增加图表日期筛选状态"
```

---

### Task 6: 图表日期选择器与应用按钮

**Files:**
- Modify: `frontend/src/views/dashboard/components/sq-view/index.vue:103,1044,1231,1957`
- Create: `frontend/src/views/dashboard/components/sq-view/index.date-filter.test.mjs`

**Interfaces:**
- Consumes: Task 5 状态函数；现有 `refreshData(options)`。
- Produces: `applyDashboardDateRange()` 和日期操作区 UI。

- [ ] **Step 1: 写失败测试约束“选择不查询、应用才查询”**

```javascript
assert.match(source, /v-model="dateFilterState\.draftRange"/)
assert.match(source, /@click="applyDashboardDateRange"/)
assert.doesNotMatch(dateChangeHandler, /refreshData\(/)
assert.match(applyHandler, /refreshData\([\s\S]*forceRefresh:\s*true/)
assert.match(source, /dateFilterCapability[\s\S]*status\s*===\s*'available'/)
```

- [ ] **Step 2: 运行并确认失败**

Run from `frontend`: `node src/views/dashboard/components/sq-view/index.date-filter.test.mjs`

Expected: FAIL，日期操作区尚不存在。

- [ ] **Step 3: 接入状态和请求**

实现要求：

- 在标题下方独立日期工具栏使用 `el-date-picker type="daterange"` 和“应用”按钮。
- `disabled-date` 禁止 `maxEnd` 之后的日期。
- 只有 capability `available` 时渲染；实时和其他状态不渲染占位文字。
- `refreshData` 增加可选 `pivotOverride`，请求时使用临时 pivot，不写 `props.viewInfo.pivot`。
- `applyDashboardDateRange` 设置 pending/applying，调用 `refreshData({ forceRefresh: true, blocking: true, pivotOverride })`。
- `refreshData` 返回明确 `boolean`；成功后提交 applied，失败后保留旧数据、旧 applied 和新 draft。
- 成功响应中的 `date_filter_capability` 必须规范化写入当前内存对象的 `viewInfo.dateFilterCapability`，不得持久化。
- 请求序列号继续防止旧响应覆盖新响应。
- 删除现有日期选择后自动调用 `schedulePivotRefresh()` 的路径；粒度和分组行为保持现状。
- 容器窄于约 560px 时工具栏换行，标题和右侧操作不重叠。

- [ ] **Step 4: 运行组件回归与构建**

Run from `frontend`:

```powershell
node src/views/dashboard/components/sq-view/index.date-filter.test.mjs
node src/views/dashboard/components/sq-view/index.refresh-policy.test.mjs
node src/views/dashboard/components/sq-view/index.pivot-group.test.mjs
npm run build
```

Expected: 全部退出码 0。

- [ ] **Step 5: 提交**

```powershell
git add -- frontend/src/views/dashboard/components/sq-view/index.vue frontend/src/views/dashboard/components/sq-view/index.date-filter.test.mjs
git commit -m "功能：增加图表日期选择和应用"
```

---

### Task 7: 首次默认加载、推荐看板覆盖与全量验证

**Files:**
- Modify: `frontend/src/views/dashboard/preview/SQPreviewShow.vue:89,342,530,595`
- Create: `frontend/src/views/dashboard/preview/SQPreviewShow.date-filter.test.mjs`

**Interfaces:**
- Consumes: `buildDashboardDatePivot()` from Task 5 和后端 `dateFilterCapability`。
- Produces: 缓存优先、数据库并发 2 的默认近 14 天首次加载。

- [ ] **Step 1: 写失败测试覆盖默认请求、逐图隔离和两种看板模式**

```javascript
assert.match(source, /dateFilterCapability/)
assert.match(chartPayload, /buildDashboardDatePivot/)
assert.match(source, /CHART_DATABASE_REFRESH_CONCURRENCY\s*=\s*2/)
assert.match(source, /DASHBOARD_MODE_DEFAULT/)
assert.doesNotMatch(source, /localStorage|sessionStorage/)
```

- [ ] **Step 2: 运行并确认失败**

Run from `frontend`: `node src/views/dashboard/preview/SQPreviewShow.date-filter.test.mjs`

Expected: FAIL，初始请求尚未携带默认范围且数据库并发仍为 4。

- [ ] **Step 3: 接入默认日期与缓存队列**

实现要求：

- `collectNormalizedDashboardCharts` 为每个 `available` 图表初始化独立、非持久化日期状态。
- `chartSqlPayload` 对 `available` 图表传临时默认 custom pivot；其他图表保持现有 payload。
- 首次仍先 `cache_only`，未命中才进数据库刷新队列。
- 默认日期结果完成前不显示旧全范围快照；应用失败时保留当前已成功快照。
- 将 `CHART_DATABASE_REFRESH_CONCURRENCY` 从 4 调整为 2，避免默认日期上线后同时压测数据源。
- `default`（推荐看板）和 `my` 模式走同一路径；`platformTemplate`、mixed、external snapshot 保持原行为。
- 切换看板、刷新页面和工作空间切换时销毁日期状态，恢复后端默认范围。
- 不调用 `dashboardApi.update_canvas`、浏览器存储或任何保存动作。

- [ ] **Step 4: 运行前端相关测试和构建**

Run from `frontend`:

```powershell
node src/views/dashboard/preview/SQPreviewShow.date-filter.test.mjs
node src/views/dashboard/preview/SQPreviewShow.permission-refresh.test.mjs
node src/views/dashboard/preview/SQPreviewShow.loading-state.test.mjs
node src/views/dashboard/preview/SQPreviewShow.no-roi.test.mjs
npm run build
```

Expected: 全部退出码 0。

- [ ] **Step 5: 运行后端全量相关回归**

Run from repository root:

```powershell
backend\.venv\Scripts\python.exe -m pytest tests/test_dashboard_date_filter.py tests/test_dashboard_service.py backend/tests/test_dashboard_permission_cache.py -q
```

Expected: PASS，无失败。

- [ ] **Step 6: 浏览器只读验收**

使用不写数据库的测试 fixture 或临时内存响应验证：

1. 我的看板和推荐看板各打开一张 `available` 图表。
2. 确认默认范围为昨天前 14 天且不包含今天。
3. 修改日期后确认网络面板无请求；点击“应用”后只有当前图表请求。
4. 确认最终 SQL 日期条件位于原始表谓词，而不是只在外层结果过滤。
5. 构造 `event_realtime` 图表，确认日期操作区完全隐藏。
6. 在桌面和约 520px 卡片宽度下截图，确认标题、选择器、按钮和图表不重叠。
7. 检查网络请求中没有 `update_canvas` 或其他看板保存接口。

- [ ] **Step 7: 提交**

```powershell
git add -- frontend/src/views/dashboard/preview/SQPreviewShow.vue frontend/src/views/dashboard/preview/SQPreviewShow.date-filter.test.mjs
git commit -m "功能：接入看板默认日期加载"
```

---

## Final Verification

- [ ] 运行 `git diff --check`，确认无空白错误。
- [ ] 运行 Task 7 的后端测试命令，确认全部通过。
- [ ] 从 `frontend` 运行所有本计划新增 `.test.mjs` 和 `npm run build`。
- [ ] 运行 `git status --short`，确认未生成日志、构建产物或数据库备份。
- [ ] 检查提交历史，确认没有 Alembic、seed/repair 工具、现有看板 SQL 或数据库配置数据变更。
- [ ] 将“现有图表模板迁移”保留为单独第二阶段，必须重新获得用户授权后再设计和执行。
