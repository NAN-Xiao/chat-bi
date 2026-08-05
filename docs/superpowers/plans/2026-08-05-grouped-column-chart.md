# 分组柱状图 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 新增独立的竖向分组柱状图 `grouped_column`，让它在 Smart Q&A、分析助手、聊天图表、看板及 SQL 编辑器中完整可用，并保持现有柱状图堆叠行为不变。

**Architecture:** 在现有 `Column` 渲染器中抽出显式系列布局策略，`column` 继续选择 `stackY`，新增 `GroupedColumn` 选择 `dodgeX`。前后端统一使用 `grouped_column` 协议值，复用现有 `x / y / series` 数据协议、配置复制和持久化链路，不增加数据库字段或兼容回退。

**Tech Stack:** Vue 3、TypeScript、AntV G2 5、Node test runner、Python、Pytest、YAML 提示模板。

## Global Constraints

- 仅新增竖向分组柱状图，不新增横向分组条形图。
- 不修改页面、看板网格、卡片标题、操作栏或全屏布局。
- 不改变现有 `column` 的 `stackY` 行为，也不改变现有 `bar` 行为。
- 不根据数据自动把 `column` 静默改成 `grouped_column`。
- 字段缺失、字段不在 SQL 结果中或配置无效时，不得用第一列、其他轴或相似字段替代。
- 支持“一个指标 + series”“多个指标”“多个指标 + series”三种数据形态。
- 所有规则必须领域无关，不在共享代码中加入业务表名、字段名或演示指标特例。
- 不新增数据库字段，不修改历史 Alembic 迁移。
- 工作树固定为 `D:\AIWork3\chat-bi\.worktrees\codex-grouped-column-chart`，分支固定为 `codex/grouped-column-chart`。

---

### Task 1: 新增分组柱状图渲染核心

**Files:**
- Create: `frontend/src/views/chat/component/charts/columnSeriesLayout.ts`
- Create: `frontend/src/views/chat/component/charts/columnSeriesLayout.test.mjs`
- Create: `frontend/src/views/chat/component/charts/GroupedColumn.ts`
- Modify: `frontend/src/views/chat/component/charts/Column.ts`
- Modify: `frontend/src/views/chat/component/charts/utils.ts`
- Modify: `frontend/src/views/chat/component/BaseChart.ts`
- Modify: `frontend/src/views/chat/component/index.ts`

**Interfaces:**
- Produces: `ColumnSeriesLayout = 'stacked' | 'grouped'`。
- Produces: `resolveColumnSeriesTransform(layout, hasSeries)`，返回 `stackY`、`dodgeX` 或 `undefined`。
- Produces: `ColumnOptions`，允许子类显式指定图表名和系列布局。
- Produces: `GroupedColumn extends Column`，注册协议值 `grouped_column`。
- Consumes: 现有 `processMultiQuotaData`、`processGroupedMultiQuotaData` 和 `buildMixedUnitComboOptions`。

- [ ] **Step 1: 写失败的系列布局与注册测试**

创建 `columnSeriesLayout.test.mjs`，使用 TypeScript 编译器加载纯函数，并检查渲染器接线：

```js
import assert from 'node:assert/strict'
import { existsSync, readFileSync } from 'node:fs'
import ts from 'typescript'

const helperPath = 'src/views/chat/component/charts/columnSeriesLayout.ts'
assert.equal(existsSync(helperPath), true, '应提供柱状图系列布局策略')

const source = readFileSync(helperPath, 'utf8')
const compiled = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 },
}).outputText
const moduleUrl = `data:text/javascript;base64,${Buffer.from(compiled).toString('base64')}`
const { resolveColumnSeriesTransform } = await import(moduleUrl)

assert.deepEqual(resolveColumnSeriesTransform('stacked', true), [{ type: 'stackY' }])
assert.deepEqual(resolveColumnSeriesTransform('grouped', true), [{ type: 'dodgeX' }])
assert.equal(resolveColumnSeriesTransform('grouped', false), undefined)

const columnSource = readFileSync('src/views/chat/component/charts/Column.ts', 'utf8')
const groupedSource = readFileSync('src/views/chat/component/charts/GroupedColumn.ts', 'utf8')
const utilsSource = readFileSync('src/views/chat/component/charts/utils.ts', 'utf8')
const registrySource = readFileSync('src/views/chat/component/index.ts', 'utf8')
const baseSource = readFileSync('src/views/chat/component/BaseChart.ts', 'utf8')

assert.match(columnSource, /resolveColumnSeriesTransform\(this\.seriesLayout/)
assert.match(groupedSource, /chartName:\s*'grouped_column'/)
assert.match(groupedSource, /seriesLayout:\s*'grouped'/)
assert.match(utilsSource, /intervalTransform/)
assert.match(registrySource, /grouped_column:\s*GroupedColumn/)
assert.match(baseSource, /\| 'grouped_column'/)
```

- [ ] **Step 2: 运行测试并确认因功能缺失而失败**

Run:

```powershell
cd frontend
node --test src/views/chat/component/charts/columnSeriesLayout.test.mjs
```

Expected: FAIL，提示缺少 `columnSeriesLayout.ts` 或 `GroupedColumn.ts`。

- [ ] **Step 3: 实现纯布局策略**

在 `columnSeriesLayout.ts` 中加入：

```ts
export type ColumnSeriesLayout = 'stacked' | 'grouped'

export type ColumnSeriesTransform = {
  type: 'stackY' | 'dodgeX'
}

export function resolveColumnSeriesTransform(
  layout: ColumnSeriesLayout,
  hasSeries: boolean
): ColumnSeriesTransform[] | undefined {
  if (!hasSeries) return undefined
  return [{ type: layout === 'grouped' ? 'dodgeX' : 'stackY' }]
}
```

- [ ] **Step 4: 让 Column 复用显式布局策略**

在 `Column.ts` 导入布局类型和函数，增加选项并保持默认值不变：

```ts
export type ColumnOptions = {
  chartName?: 'column' | 'grouped_column'
  seriesLayout?: ColumnSeriesLayout
}

export class Column extends BaseG2Chart {
  private readonly seriesLayout: ColumnSeriesLayout

  constructor(mountTarget: ChartMountTarget, options: ColumnOptions = {}) {
    super(mountTarget, options.chartName || 'column')
    this.seriesLayout = options.seriesLayout || 'stacked'
  }
```

普通 interval 配置完成后使用纯函数，不再硬编码 `stackY`：

```ts
options.transform = resolveColumnSeriesTransform(
  this.seriesLayout,
  series.length > 0
) as G2Spec['transform']
```

混合单位组合图只在 `grouped` 模式给柱形子图传入 `dodgeX`，避免改变现有 `column` 的组合图行为：

```ts
const intervalTransform =
  this.seriesLayout === 'grouped'
    ? resolveColumnSeriesTransform('grouped', mixedUnitData.countData.length > 0)
    : undefined

const options = buildMixedUnitComboOptions(
  this.chart.options(),
  axes.x[0],
  mixedUnitData,
  this.showLabel,
  responsive,
  intervalTransform as G2Spec['transform']
)
```

在 `utils.ts` 的 `buildMixedUnitComboOptions` 最后增加可选参数，并只把它赋给 interval 子图：

```ts
export function buildMixedUnitComboOptions(
  baseOptions: G2Spec,
  xAxis: ChartAxis,
  mixedData: MixedUnitChartData,
  showLabel: boolean,
  responsive: G2ResponsiveStyle = resolveG2ResponsiveStyle(undefined, 'cartesian'),
  intervalTransform?: G2Spec['transform']
): G2Spec {
```

```ts
{
  type: 'interval',
  transform: intervalTransform,
  data: mixedData.countData,
}
```

这里只在现有 interval 子对象的 `type` 与 `data` 之间插入 `transform: intervalTransform`；该子对象已有的 `encode`、`scale`、`axis`、`style`、`labels` 和 `tooltip` 属性原样保留。

- [ ] **Step 5: 新增 GroupedColumn 并注册类型**

创建 `GroupedColumn.ts`：

```ts
import type { ChartMountTarget } from '@/views/chat/component/BaseChart.ts'
import { Column } from '@/views/chat/component/charts/Column.ts'

export class GroupedColumn extends Column {
  constructor(mountTarget: ChartMountTarget) {
    super(mountTarget, {
      chartName: 'grouped_column',
      seriesLayout: 'grouped',
    })
  }
}
```

在 `BaseChart.ts` 的 `ChartTypes` 联合中加入 `'grouped_column'`。在 `component/index.ts` 导入 `GroupedColumn`，并在 `CHART_TYPE_MAP` 中加入：

```ts
grouped_column: GroupedColumn,
```

- [ ] **Step 6: 运行渲染测试与类型检查**

Run:

```powershell
cd frontend
node --test src/views/chat/component/charts/columnSeriesLayout.test.mjs
node --test src/views/chat/component/charts/g2Responsive.test.mjs
npx vue-tsc -b --pretty false
```

Expected: 三个命令均退出码 0；测试确认 `column` 解析为 `stackY`，`grouped_column` 解析为 `dodgeX`。

- [ ] **Step 7: 提交渲染核心**

```powershell
git add frontend/src/views/chat/component/charts/columnSeriesLayout.ts frontend/src/views/chat/component/charts/columnSeriesLayout.test.mjs frontend/src/views/chat/component/charts/GroupedColumn.ts frontend/src/views/chat/component/charts/Column.ts frontend/src/views/chat/component/charts/utils.ts frontend/src/views/chat/component/BaseChart.ts frontend/src/views/chat/component/index.ts
git commit -m "功能：新增分组柱状图渲染器"
```

---

### Task 2: 接入全部前端入口与展示语义

**Files:**
- Create: `frontend/src/views/chat/component/groupedColumnSurfaces.test.mjs`
- Modify: `frontend/src/views/chat/chat-block/ChartBlock.vue`
- Modify: `frontend/src/views/dashboard/components/sq-view/index.vue`
- Modify: `frontend/src/views/dashboard/common/DashboardSqlEditor.vue`
- Modify: `frontend/src/views/analysis-assistant/AnalysisAssistantDock.vue`
- Modify: `frontend/src/views/chat/component/chartInsight.ts`
- Modify: `frontend/src/views/chat/component/ChartInsightHeader.vue`
- Modify: `frontend/src/views/dashboard/utils/chartSizing.ts`
- Modify: `frontend/src/i18n/zh-CN.json`
- Modify: `frontend/src/i18n/zh-TW.json`
- Modify: `frontend/src/i18n/en.json`
- Modify: `frontend/src/i18n/ko-KR.json`

**Interfaces:**
- Consumes: `ChartTypes` 中的 `grouped_column` 和 Task 1 的图表工厂注册。
- Produces: 聊天与看板类型菜单中的“分组柱状图”选项。
- Produces: SQL 编辑器可保存及预览 `grouped_column`。
- Produces: 洞察摘要、推荐尺寸和分析助手标签将新类型视为柱状比较图。

- [ ] **Step 1: 写失败的前端入口契约测试**

创建 `groupedColumnSurfaces.test.mjs`：

```js
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import ts from 'typescript'

const read = (path) => readFileSync(path, 'utf8')

for (const path of [
  'src/views/chat/chat-block/ChartBlock.vue',
  'src/views/dashboard/components/sq-view/index.vue',
  'src/views/dashboard/common/DashboardSqlEditor.vue',
]) {
  assert.match(read(path), /grouped_column/, `${path} 必须提供分组柱状图入口`)
}

assert.match(read('src/views/analysis-assistant/AnalysisAssistantDock.vue'), /grouped_column:\s*'分组柱状图'/)
assert.match(read('src/views/chat/component/chartInsight.ts'), /grouped_column/)
assert.match(read('src/views/chat/component/ChartInsightHeader.vue'), /grouped_column/)

const labels = {
  'src/i18n/zh-CN.json': '分组柱状图',
  'src/i18n/zh-TW.json': '分組柱狀圖',
  'src/i18n/en.json': 'Grouped Column',
  'src/i18n/ko-KR.json': '그룹 세로 막대 차트',
}
for (const [path, expected] of Object.entries(labels)) {
  const messages = JSON.parse(read(path))
  assert.equal(messages.chat.chart_type.grouped_column, expected)
}

const sizingSource = read('src/views/dashboard/utils/chartSizing.ts')
const compiled = ts.transpileModule(sizingSource, {
  compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 },
}).outputText
const moduleUrl = `data:text/javascript;base64,${Buffer.from(compiled).toString('base64')}`
const { getRecommendedDashboardChartFrame } = await import(moduleUrl)
assert.deepEqual(
  getRecommendedDashboardChartFrame({ chart: { type: 'grouped_column' } }, 3),
  getRecommendedDashboardChartFrame({ chart: { type: 'column' } }, 3)
)
```

- [ ] **Step 2: 运行测试并确认入口缺失**

Run:

```powershell
cd frontend
node --test src/views/chat/component/groupedColumnSurfaces.test.mjs
```

Expected: FAIL，首先命中聊天类型菜单或多语言中缺少 `grouped_column`。

- [ ] **Step 3: 接入聊天、看板和 SQL 编辑器**

在 `ChartBlock.vue` 的柱状/条形/折线/面积兼容分支中加入 `case 'grouped_column'`，并紧邻普通柱状图加入：

```ts
pushChartType('column', Histogram)
pushChartType('grouped_column', Histogram)
```

漏斗图当前允许切换为柱状图的位置也加入相同的 `grouped_column` 选项，不改变菜单容器或样式。

在 `sq-view/index.vue` 的相同兼容分支加入 `case 'grouped_column'`，并使用现有柱状图图标：

```ts
pushChartType('grouped_column', ICON_COLUMN)
```

在 `DashboardSqlEditor.vue` 的 `chartTypes` 中紧邻 `column` 加入：

```ts
{ label: 'grouped_column', value: 'grouped_column' },
```

把多指标分组名称配置的允许列表扩展为：

```ts
['column', 'grouped_column', 'bar', 'line', 'area'].includes(form.chartType)
```

保留现有 `buildChart()`、预览和字段校验逻辑；它们继续通过 `form.chartType`、`xAxis`、`yAxis` 和 `series` 原样构造配置，不增加字段回退。

- [ ] **Step 4: 接入分析标签、洞察和推荐尺寸**

在 `AnalysisAssistantDock.vue` 的完整 `Record<ChartTypes, string>` 标签表加入：

```ts
grouped_column: '分组柱状图',
```

在 `chartInsight.ts` 的 `TOP_RICH_SUMMARY_TYPES`、`ChartInsightHeader.vue` 的 `rankedChartTypes` 和 `conversionSummaryChartTypes` 中加入 `grouped_column`，使它复用柱状比较图摘要规则。

在 `chartSizing.ts` 中将推荐尺寸判断改为集合写法，保持外层尺寸与 `column` 完全一致：

```ts
if (['line', 'area', 'bar', 'column', 'grouped_column', 'scatter'].includes(chartType)) {
  return {
    sizeX: chartCount <= 2 ? DEFAULT_DASHBOARD_GRID_COLUMNS : 48,
    sizeY: 18,
  }
}
```

- [ ] **Step 5: 增加四语种名称**

在四个 `chat.chart_type` 节点分别加入：

```json
"grouped_column": "分组柱状图"
```

```json
"grouped_column": "分組柱狀圖"
```

```json
"grouped_column": "Grouped Column"
```

```json
"grouped_column": "그룹 세로 막대 차트"
```

- [ ] **Step 6: 运行入口测试、现有洞察测试和类型检查**

Run:

```powershell
cd frontend
node --test src/views/chat/component/groupedColumnSurfaces.test.mjs
node --test src/views/chat/component/chartInsight.compact-summary.test.mjs src/views/chat/component/chartInsight.layout-stability.test.mjs
node --test src/views/dashboard/components/sq-view/insightFrame.stability.test.mjs
npx vue-tsc -b --pretty false
```

Expected: 所有命令退出码 0；新类型拥有完整入口，现有洞察布局测试继续通过。

- [ ] **Step 7: 提交前端入口**

```powershell
git add frontend/src/views/chat/component/groupedColumnSurfaces.test.mjs frontend/src/views/chat/chat-block/ChartBlock.vue frontend/src/views/dashboard/components/sq-view/index.vue frontend/src/views/dashboard/common/DashboardSqlEditor.vue frontend/src/views/analysis-assistant/AnalysisAssistantDock.vue frontend/src/views/chat/component/chartInsight.ts frontend/src/views/chat/component/ChartInsightHeader.vue frontend/src/views/dashboard/utils/chartSizing.ts frontend/src/i18n/zh-CN.json frontend/src/i18n/zh-TW.json frontend/src/i18n/en.json frontend/src/i18n/ko-KR.json
git commit -m "功能：接入分组柱状图前端入口"
```

---

### Task 3: 扩展 Smart Q&A、分析助手和看板 AI 类型协议

**Files:**
- Create: `backend/tests/test_grouped_column_chart_contract.py`
- Modify: `backend/tests/test_chart_config_sanitize.py`
- Modify: `backend/common/utils/chart_config.py`
- Modify: `backend/templates/template.yaml`
- Modify: `backend/templates/sql_examples/Oracle.yaml`
- Modify: `backend/apps/analysis_assistant/api/analysis_assistant.py`
- Modify: `backend/apps/dashboard/crud/ai_sql_generator.py`

**Interfaces:**
- Produces: 后端通用及分析助手 `CHART_TYPES` 接受 `grouped_column`。
- Produces: Smart Q&A 图表生成模板可显式输出 `grouped_column`。
- Produces: 分析助手规划提示和看板 AI SQL 输出协议包含新类型。
- Consumes: Task 1 和 Task 2 已注册的前端协议值。

- [ ] **Step 1: 写失败的后端类型与提示契约测试**

创建 `test_grouped_column_chart_contract.py`：

```py
from apps.analysis_assistant.api.analysis_assistant import (
    PLAN_PROMPT,
    FORECAST_PLAN_PROMPT,
    CHART_TYPES as ANALYSIS_CHART_TYPES,
)
from apps.chat.models.chat_model import AiModelQuestion
from apps.dashboard.crud.ai_sql_generator import _dashboard_sql_system_prompt
from apps.template.generate_chart.generator import get_chart_template
from apps.template.template import get_sql_template
from common.utils.chart_config import CHART_TYPES as SHARED_CHART_TYPES


def test_grouped_column_is_a_supported_platform_chart_type() -> None:
    assert "grouped_column" in SHARED_CHART_TYPES
    assert "grouped_column" in ANALYSIS_CHART_TYPES


def test_smart_qa_prompts_define_explicit_grouped_column_semantics() -> None:
    question = AiModelQuestion(engine="PostgreSQL", db_schema="【DB_ID】 test\n【Schema】")
    sql_rules = question.sql_sys_question("postgresql")["rules"]
    chart_rules = get_chart_template()["generate_rules"]
    combined = f"{sql_rules}\n{chart_rules}"

    assert "分组柱状图(grouped_column)" in combined
    assert '"type":"grouped_column"' in chart_rules
    assert "明确要求分组、并排或同组比较" in combined
    assert "不能仅因为结果包含多个字段" in combined


def test_analysis_and_dashboard_prompts_accept_grouped_column() -> None:
    assert "grouped_column" in PLAN_PROMPT
    assert "grouped_column" in FORECAST_PLAN_PROMPT
    assert "grouped_column" in _dashboard_sql_system_prompt()
    assert "grouped_column" in get_sql_template("oracle")["template"]["process_check"]
```

在 `test_chart_config_sanitize.py` 增加顶层图表对象用例，证明通用识别集合会处理新类型：

```py
def test_sanitize_chart_display_names_recognizes_grouped_column() -> None:
    chart = {
        "type": "grouped_column",
        "columns": [{"value": "date", "name": "date"}],
    }

    sanitized = sanitize_chart_display_names(chart)

    assert sanitized["columns"] == [{"value": "date"}]
```

- [ ] **Step 2: 运行测试并确认类型与提示缺失**

Run:

```powershell
cd backend
D:\AIWork3\chat-bi\backend\.venv\Scripts\python.exe -m pytest tests/test_grouped_column_chart_contract.py tests/test_chart_config_sanitize.py -q
```

Expected: FAIL，`grouped_column` 不在后端集合或提示模板中。

- [ ] **Step 3: 扩展通用后端类型集合**

在 `backend/common/utils/chart_config.py` 中使用完整集合：

```py
CHART_TYPES = {
    "table",
    "metric",
    "column",
    "grouped_column",
    "bar",
    "line",
    "area",
    "pie",
    "funnel",
    "heatmap",
    "scatter",
    "sankey",
    "treemap",
}
```

在 `backend/apps/analysis_assistant/api/analysis_assistant.py` 中使用完整集合：

```py
CHART_TYPES = {
    "table",
    "bar",
    "column",
    "grouped_column",
    "line",
    "area",
    "pie",
    "metric",
    "funnel",
    "heatmap",
    "scatter",
    "sankey",
    "treemap",
}
```

不要修改历史迁移 `backend/alembic/versions/121_remove_hidden_chart_display_names.py`。

- [ ] **Step 4: 扩展 Smart Q&A 图表生成模板**

在 `backend/templates/template.yaml` 的 `template.sql.process_check`、`template.sql.generate_rules`、`template.chart.generate_rules` 和 `template.guess.system` 中，把全部支持类型清单、SQL 生成步骤、字段约束组和推荐问题清单加入“分组柱状图(grouped_column)”及协议值。

在类型选择规则中加入以下明确语义：

```text
只有当用户明确要求分组、并排或同组比较，或者问题明确要求比较同一横轴分类内的不同系列数值时，才使用分组柱状图(grouped_column)。不能仅因为结果包含多个字段就选择 grouped_column；时间趋势仍优先使用 line 或 area。
```

在普通柱状图 JSON 示例之后加入分组柱状图示例：

```text
如果需要分组柱状图，JSON 格式应为：
{{"type":"grouped_column","title":"标题","axis":{{"x":{{"value":"SQL 查询维度轴的列"}},"y":[{{"value":"SQL 查询数值轴的列"}}],"series":{{"value":"SQL 查询分类的列"}}}}}}
```

同一规则必须说明：无 `series` 时允许用多个 `y` 指标形成指标系列；同时存在多个 `y` 和 `series` 时保留全部显式字段，由前端组合成“分类 / 指标”系列；不得补造 SQL 未输出的字段。

在 `backend/templates/sql_examples/Oracle.yaml` 的流程类型清单中加入 `grouped_column`，保持 Oracle 与基础协议一致。

- [ ] **Step 5: 扩展分析助手和看板 AI 输出协议**

在 `analysis_assistant.py` 的 `PLAN_PROMPT`、`FORECAST_PLAN_PROMPT` 两处 JSON 类型枚举中加入 `grouped_column`。在两处选择规则中加入同一通用约束：仅在明确分组/并排比较意图下选择，不因多个字段自动选择，时间趋势继续优先 `line/area`。

在 `ai_sql_generator.py` 的输出 JSON 契约中改为：

```text
"chart_type":"table|line|bar|column|grouped_column|pie|area|metric|scatter|heatmap|funnel|sankey|treemap"
```

不增加按业务字段名判断类型的代码分支。

- [ ] **Step 6: 运行后端定向测试**

Run:

```powershell
cd backend
D:\AIWork3\chat-bi\backend\.venv\Scripts\python.exe -m pytest tests/test_grouped_column_chart_contract.py tests/test_chart_config_sanitize.py tests/test_chart_config_postprocess.py tests/test_sql_generation_template.py -q
```

Expected: 所有测试通过；新类型被允许，提示规则明确且现有图表后处理测试无回归。

- [ ] **Step 7: 提交后端协议**

```powershell
git add backend/tests/test_grouped_column_chart_contract.py backend/tests/test_chart_config_sanitize.py backend/common/utils/chart_config.py backend/templates/template.yaml backend/templates/sql_examples/Oracle.yaml backend/apps/analysis_assistant/api/analysis_assistant.py backend/apps/dashboard/crud/ai_sql_generator.py
git commit -m "功能：支持生成分组柱状图配置"
```

---

### Task 4: 完整回归与浏览器验收

**Files:**
- Verify only; 失败时只修正前述任务列出的功能文件及对应测试。

**Interfaces:**
- Consumes: 前三个任务的 `grouped_column` 渲染、入口和后端协议。
- Produces: 桌面与窄屏下可验证的完整用户流程。

- [ ] **Step 1: 运行全部前端定向测试**

Run:

```powershell
cd frontend
node --test src/views/chat/component/charts/columnSeriesLayout.test.mjs src/views/chat/component/groupedColumnSurfaces.test.mjs
$tests = Get-ChildItem -Path 'src\views\chat\component' -Recurse -Filter '*.test.mjs' | Select-Object -ExpandProperty FullName
node --test $tests
node --test src/views/dashboard/components/sq-view/insightFrame.stability.test.mjs src/views/dashboard/utils/dashboardChartConfig.test.mjs
```

Expected: 所有测试退出码 0，无失败、跳过或未处理异常。

- [ ] **Step 2: 运行后端定向测试**

Run:

```powershell
cd backend
D:\AIWork3\chat-bi\backend\.venv\Scripts\python.exe -m pytest tests/test_grouped_column_chart_contract.py tests/test_chart_config_sanitize.py tests/test_chart_config_postprocess.py tests/test_sql_generation_template.py tests/test_analysis_assistant_sql_generation.py -q
```

Expected: 所有测试通过。

- [ ] **Step 3: 运行前端生产构建与差异检查**

Run:

```powershell
cd frontend
npm run build
cd ..
git diff --check
git status --short --branch
```

Expected: `vue-tsc -b` 和 Vite 构建成功；`git diff --check` 无输出；状态只包含本功能文件。

- [ ] **Step 4: 检查或启动本地四进程栈**

在任务工作树根目录运行：

```powershell
.\tools\stack-local.ps1 -Action status -BackendPorts 8000 -StartMcp -SkipDatabase -SkipRedis -SkipNginx
Get-NetTCPConnection -LocalPort 5173 -State Listen -ErrorAction SilentlyContinue | Select-Object LocalAddress,LocalPort,OwningProcess
```

若当前工作树的服务尚未运行且端口空闲，运行：

```powershell
.\tools\stack-local.ps1 -Action start -BackendPorts 8000 -StartMcp -SkipDatabase -SkipRedis -SkipNginx
$workspaceRoot=(Resolve-Path '.').Path
$runtimeRoot=Join-Path $workspaceRoot '.codex-runtime'
Start-Process -FilePath 'C:\Windows\System32\cmd.exe' -WorkingDirectory (Join-Path $workspaceRoot 'frontend') -ArgumentList '/c','npm run dev' -RedirectStandardOutput (Join-Path $runtimeRoot 'frontend-5173.current.out.log') -RedirectStandardError (Join-Path $runtimeRoot 'frontend-5173.current.err.log') -WindowStyle Hidden
```

启动后再次执行状态命令，并从运行时配置或启动日志输出确认：

```text
LLM_REQUEST_TIMEOUT=120
LLM_TASK_MAX_WAIT_SECONDS=900
LLM_MAX_RETRIES=1
```

Expected: frontend `5173`、API `8000`、MCP `8001` 和一个使用同一 `local-*` 队列的 Worker 均可用。端口被其他工作区占用时不得停止或覆盖其他工作区进程，应记录该阻塞并完成其余自动化验证。

- [ ] **Step 5: 使用浏览器验证 Smart Q&A 与图表切换**

使用 Browser 技能打开 `http://127.0.0.1:5173/`，选择已授权的 `SLG BI Mock` 演示数据源并提问：

```text
按日期用分组柱状图并排比较最近28天的 DAU、WAU 和 MAU
```

验证：

- 返回图表类型为“分组柱状图”。
- 每个日期下的 DAU、WAU、MAU 从同一基线并排显示，不是上下堆叠。
- 提示框和图例系列名称稳定，数据标签没有相互遮挡。
- 切换为普通“柱状图”后仍使用原有堆叠行为，再切回“分组柱状图”恢复并排。
- 添加到看板后，类型、`xAxis`、`yAxis`、`series`、SQL、结果数据、洞察和透视配置保持完整。
- 刷新看板和打开全屏后仍为分组柱状图。

- [ ] **Step 6: 验证页面布局与画布像素**

在桌面视口 `1440x900` 和窄屏视口 `390x844` 分别截图，检查：

- 图表画布非空且柱形像素可见。
- 类型菜单文本不溢出，菜单、标题、图例和操作按钮不重叠。
- 卡片外框、看板网格尺寸、标题和操作栏位置与切换前一致。
- 窄屏仅触发现有标签隐藏和柱宽收缩，不扩大页面或卡片布局。

浏览器验收结束后清理研究页签，只保留用户需要继续查看的本地应用页签。

- [ ] **Step 7: 最终确认提交范围**

Run:

```powershell
git log --oneline --decorate -5
git status --short --branch
git diff HEAD~3 --stat
git diff HEAD~3 --check
```

Expected: 分支包含设计文档、实现计划和三个中文功能提交；工作树干净；差异只涉及本计划列出的分组柱状图文件。
