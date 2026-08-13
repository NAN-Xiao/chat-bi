# 全平台独立环形图实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为 Smart Q&A、分析助手和看板新增独立 `donut` 图表类型，保持现有 `pie` 行为不变。

**Architecture:** 抽取共享径向分区图基类，由 `Pie` 和 `Donut` 提供不同内半径及标签策略。图表配置继续使用 `y + series`，通过统一类型谓词接入所有前端入口，并在后端图表白名单和提示模板中显式放行。

**Tech Stack:** Vue 3、TypeScript、AntV G2 5、Node test、Python、pytest。

## Global Constraints

- `donut` 是独立类型，不得把现有 `pie` 静默改成环形图。
- 中心保持空白，`innerRadius` 固定为 `0.55`。
- 标签和 tooltip 显示分类、数值和占比，占比最多两位小数。
- AI 仅在用户明确要求环形图时选择 `donut`。
- 不新增数据库迁移，不修改数据库方言 SQL 示例。
- 无效字段或数据必须显式报错，不得自动换字段、聚合或降级图表。

---

### Task 1: 径向图数据与渲染核心

**Files:**
- Create: `frontend/src/views/chat/component/charts/radialPartition.ts`
- Create: `frontend/src/views/chat/component/charts/RadialPartitionChart.ts`
- Create: `frontend/src/views/chat/component/charts/Donut.ts`
- Modify: `frontend/src/views/chat/component/charts/Pie.ts`
- Test: `frontend/src/views/chat/component/charts/radialPartition.test.mjs`

**Interfaces:**
- Produces: `prepareRadialSlices(data, categoryField, valueField, maxCategories?)`、`formatRadialPercentage(value, total)`、`RadialPartitionChart`、`Donut`。

- [ ] **Step 1: Write the failing test**

```js
test('prepareRadialSlices returns category values and percentages', () => {
  const result = prepareRadialSlices([{ range: 'A', count: 1 }, { range: 'B', count: 3 }], 'range', 'count')
  assert.deepEqual(result.data.map((row) => row.shuzhi_radial_percentage), [25, 75])
  assert.equal(result.total, 4)
})
```

增加缺少字段、空分类、重复分类、非数字、负数、总和为零和超过 12 类的独立测试。

- [ ] **Step 2: Run test to verify it fails**

Run: `node --test src/views/chat/component/charts/radialPartition.test.mjs`
Expected: FAIL，因为 `radialPartition.ts` 尚不存在。

- [ ] **Step 3: Write minimal implementation**

```ts
export const RADIAL_PERCENTAGE_FIELD = 'shuzhi_radial_percentage'

export function formatRadialPercentage(value: number, total: number) {
  return Number(((value / total) * 100).toFixed(2)).toString()
}
```

实现严格校验并返回不修改原始输入的新数据；共享基类根据配置生成 G2 `theta` spec，`Pie` 使用 `0`，`Donut` 使用 `0.55`。

- [ ] **Step 4: Run test to verify it passes**

Run: `node --test src/views/chat/component/charts/radialPartition.test.mjs`
Expected: PASS。

- [ ] **Step 5: Commit**

```bash
git add frontend/src/views/chat/component/charts
git commit -m "功能：新增环形图渲染核心"
```

### Task 2: 前端类型与全入口接入

**Files:**
- Create: `frontend/src/views/chat/component/chartTypes.ts`
- Modify: `frontend/src/views/chat/component/BaseChart.ts`
- Modify: `frontend/src/views/chat/component/index.ts`
- Modify: `frontend/src/views/chat/chat-block/ChartBlock.vue`
- Modify: `frontend/src/views/dashboard/components/sq-view/index.vue`
- Modify: `frontend/src/views/dashboard/common/DashboardSqlEditor.vue`
- Modify: `frontend/src/views/analysis-assistant/AnalysisAssistantDock.vue`
- Modify: `frontend/src/views/chat/component/ChartInsightHeader.vue`
- Modify: `frontend/src/views/dashboard/preview/ChartFullscreenDialog.vue`
- Modify: `frontend/src/views/dashboard/utils/chartSizing.ts`
- Modify: `frontend/src/i18n/zh-CN.json`
- Modify: `frontend/src/i18n/zh-TW.json`
- Modify: `frontend/src/i18n/en.json`
- Modify: `frontend/src/i18n/ko-KR.json`
- Test: `frontend/tests/donut-chart-contract.test.mjs`

**Interfaces:**
- Consumes: `Donut` 和 `ChartTypes`。
- Produces: `isRadialPartitionChartType(type)`，供所有饼图式字段映射和布局判断复用。

- [ ] **Step 1: Write the failing test**

测试类型联合、注册表、四个选择器、四个语言文件和所有 `pie` 专用入口均包含 `donut` 或共享谓词。

- [ ] **Step 2: Run test to verify it fails**

Run: `node --test tests/donut-chart-contract.test.mjs`
Expected: FAIL，提示缺少 `donut` 注册和选择器配置。

- [ ] **Step 3: Write minimal implementation**

```ts
export function isRadialPartitionChartType(type: string): type is 'pie' | 'donut' {
  return type === 'pie' || type === 'donut'
}
```

用该谓词替换字段映射和布局中的 `pie` 专用判断，选择器新增独立 `donut` 项。

- [ ] **Step 4: Run test to verify it passes**

Run: `node --test tests/donut-chart-contract.test.mjs`
Expected: PASS。

- [ ] **Step 5: Commit**

```bash
git add frontend/src
git commit -m "功能：接入全前端环形图类型"
```

### Task 3: 显式校验错误状态

**Files:**
- Create: `frontend/src/views/chat/component/chartValidation.ts`
- Modify: `frontend/src/views/chat/component/ChartComponent.vue`
- Modify: `frontend/src/i18n/zh-CN.json`
- Modify: `frontend/src/i18n/zh-TW.json`
- Modify: `frontend/src/i18n/en.json`
- Modify: `frontend/src/i18n/ko-KR.json`
- Test: `frontend/src/views/chat/component/ChartComponent.validation.test.mjs`

**Interfaces:**
- Produces: `ChartValidationError(code)`；`ChartComponent` 对该错误显示本地化状态并跳过重试。

- [ ] **Step 1: Write the failing test**

验证校验错误会清除旧图、显示错误状态且不调用重试调度；普通 Error 仍走现有重试分支。

- [ ] **Step 2: Run test to verify it fails**

Run: `node --test src/views/chat/component/ChartComponent.validation.test.mjs`
Expected: FAIL，因为没有校验错误分支。

- [ ] **Step 3: Write minimal implementation**

```ts
export class ChartValidationError extends Error {
  constructor(public readonly code: string) {
    super(code)
    this.name = 'ChartValidationError'
  }
}
```

原子渲染捕获该错误后销毁旧实例、停止加载并展示错误；临时渲染错误保持原逻辑。

- [ ] **Step 4: Run test to verify it passes**

Run: `node --test src/views/chat/component/ChartComponent.validation.test.mjs`
Expected: PASS。

- [ ] **Step 5: Commit**

```bash
git add frontend/src/views/chat/component frontend/src/i18n
git commit -m "修复：显示环形图配置校验错误"
```

### Task 4: 后端协议和回归验证

**Files:**
- Modify: `backend/common/utils/chart_config.py`
- Modify: `backend/templates/template.yaml`
- Modify: `backend/apps/analysis_assistant/api/analysis_assistant.py`
- Modify: `backend/tests/test_chart_config_sanitize.py`
- Test: `backend/tests/test_donut_chart_contract.py`

**Interfaces:**
- Produces: 后端完整接受 `donut`，分析助手按照 `y + series` 输出配置，模板限制仅显式请求时选择。

- [ ] **Step 1: Write the failing test**

```python
def test_donut_is_a_supported_chart_type() -> None:
    assert "donut" in CHART_TYPES
```

增加模板包含显式选择规则、分析助手类型集合包含 `donut`、普通自动类型选择不返回 `donut` 的测试。

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_donut_chart_contract.py tests/test_chart_config_sanitize.py -q`
Expected: FAIL，因为后端尚未注册 `donut`。

- [ ] **Step 3: Write minimal implementation**

在统一类型集合和模板枚举中加入 `donut`，分析助手把 `donut` 视为与 `pie` 相同的字段映射类型，但不加入普通自动推荐分支。

- [ ] **Step 4: Run focused and full verification**

Run: `python -m pytest tests/test_donut_chart_contract.py tests/test_chart_config_sanitize.py tests/test_llm_sql_answer_parser.py -q`
Expected: PASS。

Run: `npm run build`
Expected: PASS。

- [ ] **Step 5: Commit**

```bash
git add backend frontend docs/superpowers/plans/2026-08-05-donut-chart.md
git commit -m "功能：完成全平台环形图协议"
```
