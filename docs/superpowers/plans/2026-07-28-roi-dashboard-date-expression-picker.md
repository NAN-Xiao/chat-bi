# ROI 看板日期表达式选择器实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在普通看板 SQL 编辑抽屉中增加配置驱动的日期表达式选择器，并仅为当前“我的看板”ROI 看板 4 张图完成受控 SQL 日期参数迁移。

**Architecture:** 前端纯函数模块定义和校验表达式，可复用 Vue 组件只编辑抽屉草稿，`DashboardSqlEditor.vue` 将同一表达式派生到 Builder 与 Pivot。后端在每次预览时按 `Asia/Shanghai` 解析表达式并复用现有 SQL token、权限、只读执行和缓存链；一次性迁移工具只通过固定资源清单与 CAS 哈希更新目标配置。

**Tech Stack:** Vue 3、TypeScript、Element Plus、dayjs、Node.js 测试、FastAPI/Pydantic、Python 3.11、pytest、PostgreSQL/psycopg、MySQL `YYYYMMDD` 分区字段

## Global Constraints

- 新组件只由 `frontend/src/views/dashboard/common/DashboardSqlEditor.vue` 调用。
- 不修改 `frontend/src/views/dashboard/components/sq-view/index.vue` 及图表卡片日期、粒度、刷新逻辑。
- 通用运行时代码不得判断“ROI 看板”名称、业务字段名、图表 ID 或资源 ID。
- 仅 `sourceConfig.sql.builder.dateExpressionPickerEnabled === true` 的图表显示新控件。
- 目标图表允许保持 `pivot.enabled = false`，但必须保留日期执行配置。
- 后端业务时区固定使用现有 `settings.DASHBOARD_BUSINESS_TIMEZONE = "Asia/Shanghai"`。
- 今日可选；合法日期范围无数据时返回成功空结果，不回退到昨日。
- 自然周期保存语义预设，不能在保存时固化成日期或天数偏移。
- 配置无效、Builder/Pivot 不一致或 token 不完整时失败关闭，不得静默回退到 `30d`。
- 目标资源 ID 只能出现在一次性迁移工具和测试中。
- 迁移默认 dry-run；`--apply` 前必须备份，更新必须使用旧值 CAS，提交后逐图读回。

---

### Task 1: 实现前端日期表达式纯函数

**Files:**
- Create: `frontend/src/views/dashboard/common/dashboardDateExpression.ts`
- Create: `frontend/src/views/dashboard/common/dashboardDateExpression.test.mjs`

**Interfaces:**
- Consumes: 显式 `now: string | Date` 与 `timezone: string`，不读取浏览器全局时间。
- Produces: `DashboardDateExpression`、`normalizeDashboardDateExpression`、`validateDashboardDateExpression`、`resolveDashboardDateExpression`、`formatDashboardDateExpression`、`cloneDashboardDateExpression`。

- [ ] **Step 1: 写失败测试，锁定预设、端点和失败关闭行为**

创建测试并通过 esbuild 加载 TypeScript：

```js
import assert from 'node:assert/strict'
import esbuild from 'esbuild'

const build = await esbuild.build({
  entryPoints: ['src/views/dashboard/common/dashboardDateExpression.ts'],
  bundle: true,
  platform: 'node',
  format: 'esm',
  write: false,
  absWorkingDir: process.cwd(),
})
const url = `data:text/javascript;base64,${Buffer.from(build.outputFiles[0].text).toString('base64')}`
const {
  ALL_TIME_END,
  ALL_TIME_START,
  cloneDashboardDateExpression,
  formatDashboardDateExpression,
  normalizeDashboardDateExpression,
  resolveDashboardDateExpression,
  validateDashboardDateExpression,
} = await import(url)

const now = '2026-07-28T12:00:00+08:00'
const expected = new Map([
  ['yesterday', ['2026-07-27', '2026-07-27']],
  ['today', ['2026-07-28', '2026-07-28']],
  ['previous_week', ['2026-07-20', '2026-07-26']],
  ['current_week', ['2026-07-27', '2026-07-28']],
  ['previous_month', ['2026-06-01', '2026-06-30']],
  ['current_month', ['2026-07-01', '2026-07-28']],
  ['past_7_days', ['2026-07-21', '2026-07-27']],
  ['recent_7_days', ['2026-07-22', '2026-07-28']],
  ['past_30_days', ['2026-06-28', '2026-07-27']],
  ['recent_30_days', ['2026-06-29', '2026-07-28']],
  ['past_90_days', ['2026-04-29', '2026-07-27']],
  ['all_time', [ALL_TIME_START, ALL_TIME_END]],
])
for (const [preset, range] of expected) {
  assert.deepEqual(
    resolveDashboardDateExpression({ version: 1, mode: 'preset', preset }, now, 'Asia/Shanghai'),
    { start: range[0], end: range[1] }
  )
}

const fixedToToday = {
  version: 1,
  mode: 'range',
  start: { mode: 'static', date: '2026-01-01' },
  end: { mode: 'dynamic', unit: 'day', offset: 0 },
}
assert.deepEqual(resolveDashboardDateExpression(fixedToToday, now, 'Asia/Shanghai'), {
  start: '2026-01-01',
  end: '2026-07-28',
})
assert.equal(validateDashboardDateExpression(fixedToToday, now, 'Asia/Shanghai').valid, true)
assert.equal(formatDashboardDateExpression({ version: 1, mode: 'preset', preset: 'past_30_days' }), '过去30天')
assert.deepEqual(normalizeDashboardDateExpression(fixedToToday), fixedToToday)
assert.notEqual(cloneDashboardDateExpression(fixedToToday), fixedToToday)

for (const invalid of [
  null,
  { version: 2, mode: 'preset', preset: 'today' },
  { version: 1, mode: 'preset', preset: 'unknown' },
  { version: 1, mode: 'range', start: { mode: 'static', date: '2026/01/01' }, end: { mode: 'dynamic', unit: 'day', offset: 0 } },
  { version: 1, mode: 'range', start: { mode: 'static', date: '2026-08-01' }, end: { mode: 'static', date: '2026-07-01' } },
]) {
  assert.equal(validateDashboardDateExpression(invalid, now, 'Asia/Shanghai').valid, false)
}
console.log('dashboard date expression tests passed')
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd frontend; node src/views/dashboard/common/dashboardDateExpression.test.mjs`

Expected: FAIL，错误包含 `Could not resolve` 或目标模块不存在。

- [ ] **Step 3: 实现类型、规范化、解析、校验与展示函数**

实现以下公共契约；日期运算统一通过 dayjs 的时区插件完成，周起点显式按周一计算：

```ts
import dayjs, { type Dayjs } from 'dayjs'
import customParseFormat from 'dayjs/plugin/customParseFormat'
import utc from 'dayjs/plugin/utc'
import timezonePlugin from 'dayjs/plugin/timezone'

dayjs.extend(customParseFormat)
dayjs.extend(utc)
dayjs.extend(timezonePlugin)

export const ALL_TIME_START = '1000-01-01'
export const ALL_TIME_END = '9999-12-31'
export const DASHBOARD_DATE_PRESETS = [
  'yesterday', 'today', 'previous_week', 'current_week',
  'previous_month', 'current_month', 'past_7_days', 'recent_7_days',
  'past_30_days', 'recent_30_days', 'past_90_days', 'all_time',
] as const
export type DashboardDatePreset = (typeof DASHBOARD_DATE_PRESETS)[number]
export type DashboardDateEndpoint =
  | { mode: 'dynamic'; unit: 'day'; offset: number }
  | { mode: 'static'; date: string }
export type DashboardDateExpression =
  | { version: 1; mode: 'preset'; preset: DashboardDatePreset }
  | { version: 1; mode: 'range'; start: DashboardDateEndpoint; end: DashboardDateEndpoint }
export type DashboardResolvedDateRange = { start: string; end: string }
export type DashboardDateExpressionValidation = { valid: boolean; message: string }

const labels: Record<DashboardDatePreset, string> = {
  yesterday: '昨日', today: '今日', previous_week: '上周', current_week: '本周',
  previous_month: '上月', current_month: '本月', past_7_days: '过去7天',
  recent_7_days: '最近7天', past_30_days: '过去30天', recent_30_days: '最近30天',
  past_90_days: '过去90天', all_time: '全部时间',
}
const isoDate = /^\d{4}-\d{2}-\d{2}$/
const textDate = (value: Dayjs) => value.format('YYYY-MM-DD')
const monday = (value: Dayjs) => value.subtract((value.day() + 6) % 7, 'day').startOf('day')

export function cloneDashboardDateExpression(value: DashboardDateExpression): DashboardDateExpression {
  return JSON.parse(JSON.stringify(value))
}

export function normalizeDashboardDateExpression(value: unknown): DashboardDateExpression | null {
  if (!value || typeof value !== 'object' || (value as any).version !== 1) return null
  if ((value as any).mode === 'preset' && DASHBOARD_DATE_PRESETS.includes((value as any).preset)) {
    return { version: 1, mode: 'preset', preset: (value as any).preset }
  }
  if ((value as any).mode !== 'range') return null
  const endpoint = (raw: any): DashboardDateEndpoint | null => {
    if (raw?.mode === 'static' && isoDate.test(raw.date || '') && dayjs(raw.date, 'YYYY-MM-DD', true).isValid()) {
      return { mode: 'static', date: raw.date }
    }
    if (raw?.mode === 'dynamic' && raw.unit === 'day' && Number.isInteger(raw.offset)) {
      return { mode: 'dynamic', unit: 'day', offset: raw.offset }
    }
    return null
  }
  const start = endpoint((value as any).start)
  const end = endpoint((value as any).end)
  return start && end ? { version: 1, mode: 'range', start, end } : null
}

export function resolveDashboardDateExpression(
  value: DashboardDateExpression,
  now: string | Date,
  timezone: string
): DashboardResolvedDateRange {
  const today = dayjs(now).tz(timezone).startOf('day')
  if (value.mode === 'range') {
    const resolve = (endpoint: DashboardDateEndpoint) => endpoint.mode === 'static'
      ? endpoint.date
      : textDate(today.add(endpoint.offset, 'day'))
    return { start: resolve(value.start), end: resolve(value.end) }
  }
  const ranges: Record<DashboardDatePreset, DashboardResolvedDateRange> = {
    yesterday: { start: textDate(today.subtract(1, 'day')), end: textDate(today.subtract(1, 'day')) },
    today: { start: textDate(today), end: textDate(today) },
    previous_week: { start: textDate(monday(today).subtract(7, 'day')), end: textDate(monday(today).subtract(1, 'day')) },
    current_week: { start: textDate(monday(today)), end: textDate(today) },
    previous_month: { start: textDate(today.subtract(1, 'month').startOf('month')), end: textDate(today.subtract(1, 'month').endOf('month')) },
    current_month: { start: textDate(today.startOf('month')), end: textDate(today) },
    past_7_days: { start: textDate(today.subtract(7, 'day')), end: textDate(today.subtract(1, 'day')) },
    recent_7_days: { start: textDate(today.subtract(6, 'day')), end: textDate(today) },
    past_30_days: { start: textDate(today.subtract(30, 'day')), end: textDate(today.subtract(1, 'day')) },
    recent_30_days: { start: textDate(today.subtract(29, 'day')), end: textDate(today) },
    past_90_days: { start: textDate(today.subtract(90, 'day')), end: textDate(today.subtract(1, 'day')) },
    all_time: { start: ALL_TIME_START, end: ALL_TIME_END },
  }
  return ranges[value.preset]
}

export function validateDashboardDateExpression(value: unknown, now: string | Date, timezone: string): DashboardDateExpressionValidation {
  const normalized = normalizeDashboardDateExpression(value)
  if (!normalized) return { valid: false, message: '日期表达式配置无效' }
  const range = resolveDashboardDateExpression(normalized, now, timezone)
  return range.start <= range.end
    ? { valid: true, message: '' }
    : { valid: false, message: '开始日期不能晚于结束日期' }
}

export function formatDashboardDateExpression(value: DashboardDateExpression): string {
  if (value.mode === 'preset') return labels[value.preset]
  const endpoint = (item: DashboardDateEndpoint) => item.mode === 'static'
    ? item.date
    : item.offset === 0 ? '今日' : `${Math.abs(item.offset)}天前`
  return `${endpoint(value.start)} 至 ${endpoint(value.end)}`
}
```

- [ ] **Step 4: 运行测试并执行类型构建**

Run: `cd frontend; node src/views/dashboard/common/dashboardDateExpression.test.mjs; npm run build`

Expected: 输出 `dashboard date expression tests passed`，随后生产构建成功。

- [ ] **Step 5: 提交纯函数任务**

```bash
git add frontend/src/views/dashboard/common/dashboardDateExpression.ts frontend/src/views/dashboard/common/dashboardDateExpression.test.mjs
git commit -m "功能：增加看板日期表达式模型"
```

---

### Task 2: 实现日期表达式选择器组件

**Files:**
- Create: `frontend/src/views/dashboard/common/DashboardDateExpressionPicker.vue`
- Create: `frontend/src/views/dashboard/common/DashboardDateExpressionPicker.test.mjs`

**Interfaces:**
- Consumes: Task 1 的 `DashboardDateExpression` 与纯函数。
- Produces: `v-model`、`apply`、`cancel` 事件；组件内部 `draft` 不直接写父表单。

- [ ] **Step 1: 写组件契约失败测试**

```js
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'

const source = readFileSync(fileURLToPath(new URL('./DashboardDateExpressionPicker.vue', import.meta.url)), 'utf8')
assert.match(source, /defineModel<DashboardDateExpression \| null>/)
assert.match(source, /cloneDashboardDateExpression/)
assert.match(source, /function openPicker/)
assert.match(source, /function cancelDraft/)
assert.match(source, /function applyDraft/)
assert.match(source, /emit\('apply', next\)/)
assert.match(source, /preset-options/)
assert.match(source, /endpoint-mode/)
assert.match(source, /picker-footer/)
assert.doesNotMatch(source, /resourceId|dashboardMode|ROI看板|sq-view/)
console.log('dashboard date expression picker contract passed')
```

- [ ] **Step 2: 运行测试确认组件不存在**

Run: `cd frontend; node src/views/dashboard/common/DashboardDateExpressionPicker.test.mjs`

Expected: FAIL with `ENOENT`。

- [ ] **Step 3: 创建组件并实现独立草稿交互**

组件实现必须包含以下状态和事件，不在组件内调用 API：

```vue
<script setup lang="ts">
import { computed, ref } from 'vue'
import {
  DASHBOARD_DATE_PRESETS,
  cloneDashboardDateExpression,
  formatDashboardDateExpression,
  resolveDashboardDateExpression,
  validateDashboardDateExpression,
  type DashboardDateEndpoint,
  type DashboardDateExpression,
  type DashboardDatePreset,
} from './dashboardDateExpression'

const props = withDefaults(defineProps<{ disabled?: boolean; timezone?: string }>(), {
  disabled: false,
  timezone: 'Asia/Shanghai',
})
const model = defineModel<DashboardDateExpression | null>({ default: null })
const emit = defineEmits<{ apply: [value: DashboardDateExpression]; cancel: [] }>()
const visible = ref(false)
const draft = ref<DashboardDateExpression>({ version: 1, mode: 'preset', preset: 'past_30_days' })
const presetLabels: Record<DashboardDatePreset, string> = {
  yesterday: '昨日', today: '今日', previous_week: '上周', current_week: '本周',
  previous_month: '上月', current_month: '本月', past_7_days: '过去7天',
  recent_7_days: '最近7天', past_30_days: '过去30天', recent_30_days: '最近30天',
  past_90_days: '过去90天', all_time: '全部时间',
}
const preview = computed(() => resolveDashboardDateExpression(draft.value, new Date(), props.timezone))
const validation = computed(() => validateDashboardDateExpression(draft.value, new Date(), props.timezone))
const buttonLabel = computed(() => model.value ? formatDashboardDateExpression(model.value) : '选择时间')

function openPicker() {
  if (props.disabled) return
  draft.value = model.value
    ? cloneDashboardDateExpression(model.value)
    : { version: 1, mode: 'preset', preset: 'past_30_days' }
  visible.value = true
}
function selectPreset(preset: DashboardDatePreset) {
  draft.value = { version: 1, mode: 'preset', preset }
}
function ensureRange() {
  if (draft.value.mode !== 'range') {
    draft.value = {
      version: 1,
      mode: 'range',
      start: { mode: 'dynamic', unit: 'day', offset: -30 },
      end: { mode: 'dynamic', unit: 'day', offset: -1 },
    }
  }
}
function setEndpointMode(side: 'start' | 'end', value: string | number | boolean) {
  const mode = value === 'static' ? 'static' : 'dynamic'
  ensureRange()
  const range = draft.value as Extract<DashboardDateExpression, { mode: 'range' }>
  range[side] = mode === 'dynamic'
    ? { mode: 'dynamic', unit: 'day', offset: side === 'start' ? -30 : -1 }
    : { mode: 'static', date: preview.value[side] }
}
function updateEndpoint(side: 'start' | 'end', value: DashboardDateEndpoint) {
  ensureRange()
  ;(draft.value as Extract<DashboardDateExpression, { mode: 'range' }>)[side] = value
}
function cancelDraft() { visible.value = false; emit('cancel') }
function applyDraft() {
  if (!validation.value.valid) return
  const next = cloneDashboardDateExpression(draft.value)
  model.value = next
  visible.value = false
  emit('apply', next)
}
</script>

<template>
  <el-popover v-model:visible="visible" :width="620" placement="bottom-start" trigger="click">
    <template #reference>
      <el-button class="date-expression-trigger" :disabled="disabled" @click="openPicker">{{ buttonLabel }}</el-button>
    </template>
    <div class="date-expression-picker">
      <header><strong>日期范围</strong><span>{{ preview.start }} → {{ preview.end }}</span></header>
      <div class="picker-body">
        <aside class="preset-options">
          <button v-for="preset in DASHBOARD_DATE_PRESETS" :key="preset" type="button" @click="selectPreset(preset)">
            {{ presetLabels[preset] }}
          </button>
          <button type="button" @click="ensureRange">自定义时间</button>
        </aside>
        <main v-if="draft.mode === 'range'" class="range-editor">
          <section v-for="side in (['start', 'end'] as const)" :key="side">
            <el-segmented class="endpoint-mode" :model-value="draft[side].mode" :options="[{ label: '动态时间', value: 'dynamic' }, { label: '静态时间', value: 'static' }]" @change="setEndpointMode(side, $event)" />
            <el-input-number v-if="draft[side].mode === 'dynamic'" :model-value="draft[side].offset" :max="0" @change="updateEndpoint(side, { mode: 'dynamic', unit: 'day', offset: Number($event) })" />
            <el-date-picker v-else :model-value="draft[side].date" type="date" value-format="YYYY-MM-DD" @update:model-value="updateEndpoint(side, { mode: 'static', date: String($event) })" />
          </section>
        </main>
        <main v-else class="preset-preview">{{ presetLabels[draft.preset] }}</main>
      </div>
      <div v-if="!validation.valid" class="picker-error">{{ validation.message }}</div>
      <footer class="picker-footer"><el-button @click="cancelDraft">取消</el-button><el-button type="primary" :disabled="!validation.valid" @click="applyDraft">应用</el-button></footer>
    </div>
  </el-popover>
</template>

<style scoped>
.date-expression-trigger { max-width: 100%; justify-content: flex-start; }
.date-expression-picker { color: #1f2329; }
.date-expression-picker header { display: flex; flex-direction: column; gap: 4px; padding: 4px 8px 12px; border-bottom: 1px solid #e5e6eb; }
.date-expression-picker header span { color: #86909c; font-size: 12px; }
.picker-body { display: grid; grid-template-columns: 150px minmax(0, 1fr); min-height: 300px; }
.preset-options { display: grid; align-content: start; gap: 4px; padding: 12px 10px; border-right: 1px solid #e5e6eb; }
.preset-options button { min-height: 30px; border: 0; border-radius: 4px; background: transparent; text-align: left; cursor: pointer; }
.preset-options button:hover { background: #f2f3f5; }
.range-editor { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 14px; padding: 16px; }
.range-editor section { display: flex; flex-direction: column; gap: 12px; min-width: 0; }
.endpoint-mode { width: 100%; }
.preset-preview { display: grid; place-items: center; color: #4e5969; }
.picker-error { color: #f53f3f; padding: 0 16px 8px; }
.picker-footer { display: flex; justify-content: flex-end; gap: 8px; padding: 10px 12px 2px; border-top: 1px solid #e5e6eb; }
@media (max-width: 720px) { .picker-body { grid-template-columns: 120px minmax(0, 1fr); } .range-editor { grid-template-columns: 1fr; } }
</style>
```

- [ ] **Step 4: 运行组件契约测试与构建**

Run: `cd frontend; node src/views/dashboard/common/DashboardDateExpressionPicker.test.mjs; npm run build`

Expected: 契约测试输出通过，Vue 类型检查与 Vite 构建通过。

- [ ] **Step 5: 提交组件任务**

```bash
git add frontend/src/views/dashboard/common/DashboardDateExpressionPicker.vue frontend/src/views/dashboard/common/DashboardDateExpressionPicker.test.mjs
git commit -m "功能：增加日期表达式选择器组件"
```

---

### Task 3: 接入 SQL 编辑抽屉保存与预览链

**Files:**
- Modify: `frontend/src/views/dashboard/common/DashboardSqlEditor.vue:245-257,1743-1775,2963-3051,4618-4660`
- Modify: `frontend/src/views/dashboard/common/DashboardSqlEditor.builder-persistence.test.mjs`
- Modify: `frontend/src/views/dashboard/common/DashboardSqlEditor.date-filter.test.mjs`
- Create: `frontend/src/views/dashboard/common/DashboardSqlEditor.date-expression.test.mjs`

**Interfaces:**
- Consumes: Task 1/2 的组件和表达式函数；持久化入口 `sourceConfig.sql.builder` 与 `viewInfo.pivot`。
- Produces: `builder.timeExpression` 为唯一编辑源；`pivot.date_expression` 为派生执行配置；关闭透视仍可预览日期 token。

- [ ] **Step 1: 写失败测试，锁定配置驱动与卡片隔离**

```js
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'

const source = readFileSync(fileURLToPath(new URL('./DashboardSqlEditor.vue', import.meta.url)), 'utf8')
assert.match(source, /DashboardDateExpressionPicker/)
assert.match(source, /dateExpressionPickerEnabled/)
assert.match(source, /timeExpression/)
assert.match(source, /date_expression/)
assert.match(source, /dateExpressionEnabled[\s\S]*previewPivotPayload/)
assert.match(source, /v-if="dateExpressionEnabled"/)
assert.match(source, /v-else[\s\S]*v-model="sqlBuilder\.timeRange"/)
assert.doesNotMatch(source, /4f08e75945c3498486963e70f3c75688|ROI看板|dashboardMode\s*===\s*['"]roi/)
const cardSource = readFileSync(fileURLToPath(new URL('../components/sq-view/index.vue', import.meta.url)), 'utf8')
assert.doesNotMatch(cardSource, /DashboardDateExpressionPicker|dateExpressionPickerEnabled|timeExpression/)
console.log('dashboard SQL editor date expression integration contract passed')
```

- [ ] **Step 2: 运行编辑器测试确认失败**

Run: `cd frontend; node src/views/dashboard/common/DashboardSqlEditor.date-expression.test.mjs`

Expected: FAIL，缺少新组件或配置字段。

- [ ] **Step 3: 增加编辑态、恢复、保存和一致性校验**

在脚本顶部导入组件及函数，并把编辑态扩展为：

```ts
import DashboardDateExpressionPicker from './DashboardDateExpressionPicker.vue'
import {
  cloneDashboardDateExpression,
  normalizeDashboardDateExpression,
  validateDashboardDateExpression,
  type DashboardDateExpression,
} from './dashboardDateExpression'

const sqlBuilder = reactive({
  // 保留现有字段
  dateExpressionPickerEnabled: false,
  timeExpression: null as DashboardDateExpression | null,
})
const dateExpressionEnabled = computed(() => sqlBuilder.dateExpressionPickerEnabled === true)
const persistedPivotDateExpression = ref<DashboardDateExpression | null>(null)
const dateExpressionConsistencyError = computed(() => {
  if (!dateExpressionEnabled.value || !sqlBuilder.timeExpression) return ''
  if (!persistedPivotDateExpression.value) return '日期表达式执行配置缺失'
  return JSON.stringify(sqlBuilder.timeExpression) === JSON.stringify(persistedPivotDateExpression.value)
    ? ''
    : '日期表达式配置不一致'
})
```

将以下字段加入现有恢复/保存函数：

```ts
// builderConfigForSave()
dateExpressionPickerEnabled: sqlBuilder.dateExpressionPickerEnabled === true,
timeExpression: sqlBuilder.timeExpression
  ? cloneDashboardDateExpression(sqlBuilder.timeExpression)
  : null,

// restoreSqlBuilderState(value)
sqlBuilder.dateExpressionPickerEnabled = value?.dateExpressionPickerEnabled === true
sqlBuilder.timeExpression = normalizeDashboardDateExpression(value?.timeExpression)
sqlBuilder.timeRange = sqlBuilder.dateExpressionPickerEnabled
  ? 'expression'
  : timeRangeValues.includes(value?.timeRange) ? value.timeRange : '30d'
```

`initPivotConfig()` 记录持久化执行表达式：

```ts
persistedPivotDateExpression.value = normalizeDashboardDateExpression(pivot?.date_expression)
```

组件“应用”后同时更新编辑源和当前派生基线：

```ts
function applyDateExpression(value: DashboardDateExpression) {
  sqlBuilder.timeExpression = cloneDashboardDateExpression(value)
  persistedPivotDateExpression.value = cloneDashboardDateExpression(value)
  sqlBuilder.timeRange = 'expression'
}
```

- [ ] **Step 4: 调整 Pivot 构造和预览，让关闭透视时仍携带日期契约**

将 `buildPivotConfig()` 和 `previewPivotPayload()` 的早退条件改为：

```ts
function buildPivotConfig(options: { includeGroupValues?: boolean } = {}) {
  if (!supportsPivotConfig.value) return { enabled: false }
  const expression = dateExpressionEnabled.value && sqlBuilder.timeExpression
    ? cloneDashboardDateExpression(sqlBuilder.timeExpression)
    : null
  if (!form.pivotEnabled && !expression) return { enabled: false }
  const config: Record<string, any> = {
    enabled: form.pivotEnabled,
    client_filter_only: props.viewInfo?.pivot?.client_filter_only === true,
    time_field: expression ? sqlBuilder.timeField : form.pivotTimeField,
    range_enabled: expression ? true : form.pivotRangeEnabled,
    date_parameter_type: form.pivotDateParameterType,
  }
  if (expression) {
    config.date_expression = expression
  }
  if (!form.pivotEnabled) return config
  Object.assign(config, {
    metric_fields: [...form.y],
    metric_aggregations: resolvePivotMetricAggregations(toAxes(form.y, { metrics: true }), sourcePreview.data),
    metric_field: form.y[0] || '',
    group_field: activePivotGroupValueField.value,
    group_enabled: Boolean(activePivotGroupValueField.value && form.pivotGroupEnabled),
    dimensions: inferredPivotDimensions(),
    granularity: form.pivotGranularity,
    range: form.pivotRange,
    custom_start: form.pivotCustomStart,
    custom_end: form.pivotCustomEnd,
    aggregation: defaultPivotAggregation(),
  })
  if (options.includeGroupValues !== false) config.group_values = unique(form.pivotGroupValues.map(normalizePivotGroupValue))
  return config
}

function previewPivotPayload() {
  if (!supportsPivotConfig.value || (!form.pivotEnabled && !dateExpressionEnabled.value)) return undefined
  return buildPivotConfig({ includeGroupValues: false })
}
```

在 `validateBeforeApply()` 与预览前置校验中加入：

```ts
if (dateExpressionEnabled.value) {
  const validation = validateDashboardDateExpression(sqlBuilder.timeExpression, new Date(), 'Asia/Shanghai')
  if (!validation.valid) { ElMessage.error(validation.message); return false }
  if (dateExpressionConsistencyError.value) { ElMessage.error(dateExpressionConsistencyError.value); return false }
  if (!sqlBuilder.timeField) { ElMessage.error('请选择时间字段'); return false }
  if (!form.pivotDateParameterType) { ElMessage.error('请选择日期参数类型'); return false }
}
```

- [ ] **Step 5: 在时间范围区域按启用标志切换组件**

保留时间字段和粒度控件，第三列改为：

```vue
<DashboardDateExpressionPicker
  v-if="dateExpressionEnabled"
  :model-value="sqlBuilder.timeExpression"
  timezone="Asia/Shanghai"
  :disabled="loading || builderLoading"
  @apply="applyDateExpression"
/>
<el-select v-else v-model="sqlBuilder.timeRange" size="small">
  <el-option v-for="item in builderTimeRangeOptions" :key="item.value" :label="item.label" :value="item.value" />
</el-select>
<el-date-picker
  v-if="!dateExpressionEnabled && sqlBuilder.timeRange === 'custom'"
  v-model="sqlBuilder.timeCustomRange"
  type="daterange"
  value-format="YYYY-MM-DD"
  start-placeholder="开始日期"
  end-placeholder="结束日期"
  size="small"
  class="builder-date-range"
/>
```

- [ ] **Step 6: 更新持久化测试并运行前端定向套件**

在 `DashboardSqlEditor.builder-persistence.test.mjs` 断言 Builder 保存/恢复包含启用标志与表达式；在 `DashboardSqlEditor.date-filter.test.mjs` 断言 `previewPivotPayload()` 在透视关闭、表达式启用时仍返回日期配置。

Run:

```powershell
cd frontend
node src/views/dashboard/common/dashboardDateExpression.test.mjs
node src/views/dashboard/common/DashboardDateExpressionPicker.test.mjs
node src/views/dashboard/common/DashboardSqlEditor.date-expression.test.mjs
node src/views/dashboard/common/DashboardSqlEditor.builder-persistence.test.mjs
node src/views/dashboard/common/DashboardSqlEditor.date-filter.test.mjs
npm run build
```

Expected: 5 个定向测试均通过，生产构建成功。

- [ ] **Step 7: 提交编辑器接入任务**

```bash
git add frontend/src/views/dashboard/common/DashboardSqlEditor.vue frontend/src/views/dashboard/common/DashboardSqlEditor.*.test.mjs
git commit -m "功能：在SQL编辑抽屉接入日期表达式"
```

---

### Task 4: 实现后端表达式解析与执行模型

**Files:**
- Modify: `backend/apps/dashboard/models/dashboard_model.py:406-427`
- Modify: `backend/apps/dashboard/crud/dashboard_date_filter.py`
- Modify: `tests/test_dashboard_date_filter.py`
- Modify: `backend/tests/test_dashboard_permission_cache.py`
- Modify: `tests/test_dashboard_service.py`

**Interfaces:**
- Consumes: `DashboardPivotRequest.date_expression: dict[str, Any] | None`。
- Produces: `resolve_dashboard_date_expression(expression, today)`；`prepare_dashboard_date_filter()` 对表达式优先解析，对旧 range 路径保持原行为。

- [ ] **Step 1: 写后端失败测试，复用前端相同日期向量**

在 `tests/test_dashboard_date_filter.py` 增加：

```python
@pytest.mark.parametrize(("preset", "expected"), [
    ("yesterday", ("2026-07-27", "2026-07-27")),
    ("today", ("2026-07-28", "2026-07-28")),
    ("previous_week", ("2026-07-20", "2026-07-26")),
    ("current_week", ("2026-07-27", "2026-07-28")),
    ("previous_month", ("2026-06-01", "2026-06-30")),
    ("current_month", ("2026-07-01", "2026-07-28")),
    ("past_7_days", ("2026-07-21", "2026-07-27")),
    ("recent_7_days", ("2026-07-22", "2026-07-28")),
    ("past_30_days", ("2026-06-28", "2026-07-27")),
    ("recent_30_days", ("2026-06-29", "2026-07-28")),
    ("past_90_days", ("2026-04-29", "2026-07-27")),
    ("all_time", ("1000-01-01", "9999-12-31")),
])
def test_date_expression_presets(preset, expected):
    assert resolve_dashboard_date_expression(
        {"version": 1, "mode": "preset", "preset": preset},
        today=date(2026, 7, 28),
    ) == tuple(date.fromisoformat(item) for item in expected)

def test_date_expression_allows_today_and_renders_every_physical_scan():
    sql = " UNION ALL ".join(
        f"select dt from t{i} where dt >= {{{{dashboard_start_yyyymmdd}}}} and dt <= {{{{dashboard_end_yyyymmdd}}}}"
        for i in range(4)
    )
    result = prepare_dashboard_date_filter(
        sql, ds_type="mysql", today=date(2026, 7, 28),
        pivot=_pivot("yyyymmdd_number", date_expression={"version": 1, "mode": "preset", "preset": "today"}),
    )
    assert result.capability["status"] == "available"
    assert result.start == result.end == "2026-07-28"
    assert result.sql.count("20260728") == 8

@pytest.mark.parametrize("expression", [
    {"version": 2, "mode": "preset", "preset": "today"},
    {"version": 1, "mode": "preset", "preset": "unknown"},
    {"version": 1, "mode": "range", "start": {"mode": "static", "date": "2026-08-01"}, "end": {"mode": "static", "date": "2026-07-01"}},
])
def test_invalid_date_expression_fails_closed(expression):
    result = prepare_dashboard_date_filter(
        "select dt from t where dt between {{dashboard_start_yyyymmdd}} and {{dashboard_end_yyyymmdd}}",
        ds_type="mysql", today=date(2026, 7, 28),
        pivot=_pivot("yyyymmdd_number", date_expression=expression),
    )
    assert result.capability == {"status": "unconfigured", "reason": "invalid_date_expression"}
```

- [ ] **Step 2: 运行后端测试确认失败**

Run: `backend\.venv\Scripts\python.exe -m pytest tests/test_dashboard_date_filter.py -q`

Expected: FAIL，缺少 `resolve_dashboard_date_expression`。

- [ ] **Step 3: 扩展 Pydantic 请求模型**

在 `DashboardPivotRequest` 增加：

```python
date_expression: Dict[str, Any] | None = None
```

保持 `enabled=False` 合法，不添加要求透视必须开启的校验。

- [ ] **Step 4: 实现后端表达式解析并接入现有 token 渲染**

在 `dashboard_date_filter.py` 增加纯函数：

```python
_DATE_EXPRESSION_PRESETS = {
    "yesterday", "today", "previous_week", "current_week", "previous_month",
    "current_month", "past_7_days", "recent_7_days", "past_30_days",
    "recent_30_days", "past_90_days", "all_time",
}

def resolve_dashboard_date_expression(expression: Any, *, today: date) -> tuple[date, date]:
    if not isinstance(expression, dict) or expression.get("version") != 1:
        raise ValueError("invalid_date_expression")
    mode = expression.get("mode")
    if mode == "preset":
        preset = expression.get("preset")
        if preset not in _DATE_EXPRESSION_PRESETS:
            raise ValueError("invalid_date_expression")
        monday = today - timedelta(days=today.weekday())
        previous_month_end = today.replace(day=1) - timedelta(days=1)
        ranges = {
            "yesterday": (today - timedelta(days=1), today - timedelta(days=1)),
            "today": (today, today),
            "previous_week": (monday - timedelta(days=7), monday - timedelta(days=1)),
            "current_week": (monday, today),
            "previous_month": (previous_month_end.replace(day=1), previous_month_end),
            "current_month": (today.replace(day=1), today),
            "past_7_days": (today - timedelta(days=7), today - timedelta(days=1)),
            "recent_7_days": (today - timedelta(days=6), today),
            "past_30_days": (today - timedelta(days=30), today - timedelta(days=1)),
            "recent_30_days": (today - timedelta(days=29), today),
            "past_90_days": (today - timedelta(days=90), today - timedelta(days=1)),
            "all_time": (date(1000, 1, 1), date(9999, 12, 31)),
        }
        return ranges[preset]
    if mode != "range":
        raise ValueError("invalid_date_expression")
    def endpoint(raw: Any) -> date:
        if not isinstance(raw, dict):
            raise ValueError("invalid_date_expression")
        if raw.get("mode") == "static":
            return _parse_date_value(raw.get("date"))
        if raw.get("mode") == "dynamic" and raw.get("unit") == "day" and isinstance(raw.get("offset"), int):
            return today + timedelta(days=raw["offset"])
        raise ValueError("invalid_date_expression")
    start, end = endpoint(expression.get("start")), endpoint(expression.get("end"))
    if start > end:
        raise ValueError("invalid_date_expression")
    return start, end
```

在 `prepare_dashboard_date_filter()` 的日期范围分支中，表达式优先，旧配置保持原限制：

```python
expression = _pivot_value(pivot, "date_expression", None)
try:
    if expression is not None:
        if isinstance(expression, dict) and expression.get("mode") == "preset" and expression.get("preset") == "all_time" \
                and not parameter_type.startswith("yyyymmdd"):
            raise ValueError("invalid_date_expression")
        start, end = resolve_dashboard_date_expression(expression, today=business_today)
    elif str(_pivot_value(pivot, "range", "") or "").strip().lower() == "custom":
        start, end = _parse_date_value(_pivot_value(pivot, "custom_start", "")), _parse_date_value(_pivot_value(pivot, "custom_end", ""))
        if start > end or start > default_end or end > default_end:
            raise ValueError("invalid_date_range")
    else:
        start, end = default_start, default_end
except (TypeError, ValueError):
    reason = "invalid_date_expression" if expression is not None else "invalid_date_range"
    return _unconfigured(source_sql, physical_tables, reason)
```

能力返回中增加 `expression`、实际 `start/end` 和业务时区，但不改变现有字段：

```python
"expression": expression,
"resolvedStart": start_text,
"resolvedEnd": end_text,
"timezone": settings.DASHBOARD_BUSINESS_TIMEZONE,
"maxEnd": business_today.isoformat() if expression is not None else default_end.isoformat(),
```

增加测试断言 `all_time` 搭配 `date` 或 `timestamp` 返回 `invalid_date_expression`；首期只有 `yyyymmdd_number/text` 可使用该预设，避免 `9999-12-31 + 1 day` 的时间戳排他边界溢出。

- [ ] **Step 5: 增加请求模型、权限顺序和缓存隔离测试**

在 `backend/tests/test_dashboard_permission_cache.py` 创建两个 `DashboardPivotRequest(enabled=False, ..., date_expression=...)`，断言：

```python
today_pivot = number_pivot.model_copy(update={
    "enabled": False,
    "date_expression": {"version": 1, "mode": "preset", "preset": "today"},
})
past_pivot = today_pivot.model_copy(update={
    "date_expression": {"version": 1, "mode": "preset", "preset": "past_30_days"},
})
assert _dashboard_sql_preview_cache_key(user, 7, rendered_today_sql, today_pivot).fingerprint != \
       _dashboard_sql_preview_cache_key(user, 7, rendered_past_sql, past_pivot).fingerprint
```

在 `tests/test_dashboard_service.py` 增加测试，mock `execute_user_query` 返回空数据并断言状态不是失败；再断言 `_dashboard_chart_permission_audit` 在 `_dashboard_sql_preview_cache_get` 前被调用。现有 `preview_sql()` 顺序应保持不变，无需为了测试改写执行架构。

- [ ] **Step 6: 运行后端定向回归**

Run:

```powershell
backend\.venv\Scripts\python.exe -m pytest tests/test_dashboard_date_filter.py backend/tests/test_dashboard_permission_cache.py tests/test_dashboard_service.py -q
```

Expected: 三个文件全部通过；旧自定义日期仍禁止今天，新 `date_expression` 路径允许今天。

- [ ] **Step 7: 提交后端任务**

```bash
git add backend/apps/dashboard/models/dashboard_model.py backend/apps/dashboard/crud/dashboard_date_filter.py tests/test_dashboard_date_filter.py backend/tests/test_dashboard_permission_cache.py tests/test_dashboard_service.py
git commit -m "功能：后端解析看板日期表达式"
```

---

### Task 5: 实现并执行目标 ROI 看板受控迁移

**Files:**
- Create: `tools/migrate_roi_dashboard_date_expression.py`
- Create: `backend/tests/test_migrate_roi_dashboard_date_expression.py`
- Runtime backup: `.codex-runtime/dashboard-date-expression-backups/`（不提交）

**Interfaces:**
- Consumes: 当前系统库 `core_dashboard.canvas_view_info`，固定资源/图表清单及当前 CAS 哈希。
- Produces: 4 张图各 4 对受控日期 token、一致 Builder/Pivot 表达式、备份清单和读回验证结果。

当前只读盘点基线：

```text
dashboard_id = 4f08e75945c3498486963e70f3c75688
tenant_id = 7482727237662281728
create_by = 7482253745313550336
canvas_sha256 = 934fe61b112d8fa1d624552185f6194a4651f5ca2afbe4d9f7f0c468463fd7da

2195201518565761024 ROI总览
  sql_sha256=12741359f1bda5147cbcf9cd21cfe98065cdbcacacb30b54e7bd772c9f3e61c4
  config_sha256=2201f2fca62029ab00ac6d4db2fe8a4f0fbc74484530010ef0c0419543c02cf6
2195202821815705600 ROI地区总览
  sql_sha256=488033a873ebb1cd916b45b74de135b15c6a27192f035e954479a2209bae0532
  config_sha256=258234e132d744e721cd4464d44955c2c7d009d516cfa41b5cd7f46840b4c8ac
2195203352126726144 ROI广告地区总览
  sql_sha256=865f76e131ce1ed57e02741df015e53f67372d29de1f09e243c153d737c41cb5
  config_sha256=5c67632b43d4a22e7285a94e6dcca551681677d00588bc817fd8e801b817f0c0
2196527317097029632 安装投放趋势
  sql_sha256=12741359f1bda5147cbcf9cd21cfe98065cdbcacacb30b54e7bd772c9f3e61c4
  config_sha256=8de04640ed8057f730a2d9f7e6e040bc3c31b9f30e62492135660e8dc2c01190
```

- [ ] **Step 1: 写迁移纯函数与安全边界失败测试**

测试必须覆盖：

```python
def test_migrate_sql_replaces_exactly_four_pairs():
    source = "\n".join(
        f"WHERE {alias}.dt >= {LEGACY_START}\nAND {alias}.dt <= {LEGACY_END}"
        for alias in ("r", "r", "v", "s")
    )
    migrated = migrate_sql(source)
    assert migrated.count(START_TOKEN) == 4
    assert migrated.count(END_TOKEN) == 4
    assert "CURDATE()" not in migrated

def test_migrate_sql_rejects_changed_occurrence_count():
    with pytest.raises(ValueError, match="固定日期条件数量不是 4 对"):
        migrate_sql(f"WHERE r.dt >= {LEGACY_START} AND r.dt <= {LEGACY_END}")

def test_migrate_view_preserves_unrelated_config():
    original = {"sql": valid_sql(), "chart": {"type": "table"}, "sourceConfig": {"sql": {}}, "pivot": {"enabled": False}}
    migrated = migrate_view(original)
    assert migrated["chart"] == original["chart"]
    assert migrated["pivot"]["enabled"] is False
    assert migrated["pivot"]["date_expression"] == DEFAULT_EXPRESSION
    assert migrated["sourceConfig"]["sql"]["builder"]["dateExpressionPickerEnabled"] is True

def test_cas_rejects_unknown_dashboard_or_chart_hash():
    with pytest.raises(RuntimeError, match="CAS 哈希不匹配"):
        validate_baseline("bad", sample_canvas())
```

- [ ] **Step 2: 运行迁移测试确认失败**

Run: `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_migrate_roi_dashboard_date_expression.py -q`

Expected: FAIL，迁移模块不存在。

- [ ] **Step 3: 实现迁移纯函数和固定清单**

工具内定义精确常量：

```python
DASHBOARD_ID = "4f08e75945c3498486963e70f3c75688"
TENANT_ID = 7482727237662281728
CREATE_BY = "7482253745313550336"
EXPECTED_CANVAS_SHA256 = "934fe61b112d8fa1d624552185f6194a4651f5ca2afbe4d9f7f0c468463fd7da"
EXPECTED = {
    "2195201518565761024": ("12741359f1bda5147cbcf9cd21cfe98065cdbcacacb30b54e7bd772c9f3e61c4", "2201f2fca62029ab00ac6d4db2fe8a4f0fbc74484530010ef0c0419543c02cf6"),
    "2195202821815705600": ("488033a873ebb1cd916b45b74de135b15c6a27192f035e954479a2209bae0532", "258234e132d744e721cd4464d44955c2c7d009d516cfa41b5cd7f46840b4c8ac"),
    "2195203352126726144": ("865f76e131ce1ed57e02741df015e53f67372d29de1f09e243c153d737c41cb5", "5c67632b43d4a22e7285a94e6dcca551681677d00588bc817fd8e801b817f0c0"),
    "2196527317097029632": ("12741359f1bda5147cbcf9cd21cfe98065cdbcacacb30b54e7bd772c9f3e61c4", "8de04640ed8057f730a2d9f7e6e040bc3c31b9f30e62492135660e8dc2c01190"),
}
LEGACY_START = "CAST(DATE_FORMAT(DATE_SUB(CURDATE(), INTERVAL 21 DAY), '%Y%m%d') AS BIGINT)"
LEGACY_END = "CAST(DATE_FORMAT(DATE_SUB(CURDATE(), INTERVAL 1 DAY), '%Y%m%d') AS BIGINT)"
START_TOKEN = "{{dashboard_start_yyyymmdd}}"
END_TOKEN = "{{dashboard_end_yyyymmdd}}"
DEFAULT_EXPRESSION = {"version": 1, "mode": "preset", "preset": "past_30_days"}

def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()

def config_fingerprint(view: dict[str, Any]) -> str:
    value = {key: view.get(key) for key in ("sourceConfig", "pivot", "datasource", "title", "name")}
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return sha256_text(raw)

def migrate_sql(sql: str) -> str:
    if sql.count(LEGACY_START) != 4 or sql.count(LEGACY_END) != 4:
        raise ValueError("固定日期条件数量不是 4 对")
    return sql.replace(LEGACY_START, START_TOKEN).replace(LEGACY_END, END_TOKEN)

def migrate_view(view: dict[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(view)
    result["sql"] = migrate_sql(str(result.get("sql") or ""))
    source_config = result.setdefault("sourceConfig", {})
    sql_config = source_config.setdefault("sql", {})
    builder = sql_config.setdefault("builder", {})
    builder.update({
        "dateExpressionPickerEnabled": True,
        "timeField": "dt",
        "timeRange": "expression",
        "timeExpression": copy.deepcopy(DEFAULT_EXPRESSION),
    })
    pivot = result.setdefault("pivot", {})
    pivot.update({
        "enabled": False,
        "time_field": "dt",
        "range_enabled": True,
        "date_parameter_type": "yyyymmdd_number",
        "date_expression": copy.deepcopy(DEFAULT_EXPRESSION),
    })
    return result
```

- [ ] **Step 4: 实现 dry-run、备份、事务 CAS、读回和回滚输出**

数据库流程必须使用：

```sql
SELECT id, tenant_id, name, create_by, update_time, canvas_view_info
FROM public.core_dashboard
WHERE id = %s AND tenant_id = %s AND create_by = %s AND COALESCE(delete_flag, 0) = 0
FOR UPDATE
```

`--apply` 分支在锁内重新计算整行与逐图哈希；备份完整查询行到 `.codex-runtime/dashboard-date-expression-backups/<timestamp>.json` 后，使用旧值 CAS：

```sql
UPDATE public.core_dashboard
SET canvas_view_info = %s, update_time = %s
WHERE id = %s
  AND tenant_id = %s
  AND create_by = %s
  AND canvas_view_info = %s
  AND COALESCE(delete_flag, 0) = 0
```

要求 `rowcount == 1`，否则回滚。提交后新连接逐图断言：4 个 start token、4 个 end token、无 `CURDATE()`、Builder/Pivot 表达式一致、非目标图表哈希不变。CLI 输出 JSON，至少包含 `applied`、`backup`、旧/新 canvas 哈希、逐图新 SQL 哈希和回滚命令；默认不传 `--apply` 时必须 `rollback()`。

CLI 参数必须显式互斥：

```python
parser = argparse.ArgumentParser(description=__doc__)
mode = parser.add_mutually_exclusive_group()
mode.add_argument("--apply", action="store_true", help="备份并迁移目标看板")
mode.add_argument("--verify", action="store_true", help="只读验证已迁移配置")
args = parser.parse_args()
```

- [ ] **Step 5: 运行迁移测试和只读 dry-run**

Run:

```powershell
backend\.venv\Scripts\python.exe -m pytest backend/tests/test_migrate_roi_dashboard_date_expression.py -q
backend\.venv\Scripts\python.exe tools/migrate_roi_dashboard_date_expression.py
```

Expected: 测试通过；dry-run 输出 `applied: false`、4 张目标图和全部 CAS 校验成功，系统库无写入。

- [ ] **Step 6: 在获得实施授权后执行迁移并逐图预览**

Run:

```powershell
backend\.venv\Scripts\python.exe tools/migrate_roi_dashboard_date_expression.py --apply
backend\.venv\Scripts\python.exe tools/migrate_roi_dashboard_date_expression.py --verify
```

Expected: `--apply` 输出备份绝对路径和 `applied: true`；`--verify` 对 4 张图返回一致配置与 token 计数。随后通过当前用户与数据源的既有 `/dashboard/sql_preview` 链分别验证 `past_30_days`、`today`、固定起点到今日；今日空结果也视为成功。

- [ ] **Step 7: 启动本地环境并完成浏览器验收**

按仓库 runbook 启动前端 `5173`、API `8000`、MCP `8001` 和一个隔离队列 Worker。打开：

```text
http://127.0.0.1:5173/#/dashboard/index?resourceId=4f08e75945c3498486963e70f3c75688&dashboardMode=my
```

逐张图验证：编辑抽屉显示新控件；取消不改配置；组件“应用”只改抽屉草稿；抽屉保存后重新打开能恢复语义；昨日、今日、上周、本月、过去 30 天和固定起点到今日可预览；桌面与窄宽度无重叠。保存前后截图，并确认 `git diff -- frontend/src/views/dashboard/components/sq-view/index.vue` 为空。

- [ ] **Step 8: 运行最终定向回归并提交迁移工具**

Run:

```powershell
backend\.venv\Scripts\python.exe -m pytest tests/test_dashboard_date_filter.py backend/tests/test_dashboard_permission_cache.py tests/test_dashboard_service.py backend/tests/test_migrate_roi_dashboard_date_expression.py -q
cd frontend
node src/views/dashboard/common/dashboardDateExpression.test.mjs
node src/views/dashboard/common/DashboardDateExpressionPicker.test.mjs
node src/views/dashboard/common/DashboardSqlEditor.date-expression.test.mjs
node src/views/dashboard/common/DashboardSqlEditor.builder-persistence.test.mjs
node src/views/dashboard/common/DashboardSqlEditor.date-filter.test.mjs
npm run build
```

Expected: 所有定向测试及生产构建通过；备份文件仍只位于 `.codex-runtime`。

```bash
git add tools/migrate_roi_dashboard_date_expression.py backend/tests/test_migrate_roi_dashboard_date_expression.py
git commit -m "迁移：启用ROI看板日期表达式"
```

---

## 完成前审查

- 使用 `code-allreview` 或 `requesting-code-review` 对任务变更做 P0-P3 审查，重点检查关闭透视的日期配置、前后端预设一致性、权限先于缓存、迁移 CAS 和非目标看板隔离。
- `git diff -- frontend/src/views/dashboard/components/sq-view/index.vue` 必须为空。
- `git status --short` 中不得出现 `.codex-runtime` 备份。
- 若迁移或浏览器验收失败，先使用备份恢复原 `canvas_view_info`，再逐图读回旧哈希；不能只回退代码而保留半迁移配置。
