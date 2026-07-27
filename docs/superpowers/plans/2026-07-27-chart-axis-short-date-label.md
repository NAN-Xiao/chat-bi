# 非明细图表日期轴短格式 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将非明细图表中严格可识别的日期横轴刻度从 `YYYY-MM-DD` 缩写为 `MM/DD`，同时保持 Tooltip、明细表和原始数据不变。

**Architecture:** 在现有 `charts/utils.ts` 增加无副作用的 `formatCategoryAxisLabel(value)`，仅处理严格的 ISO 日期或日期时间字符串。所有具有横轴的 G2 非明细图表共享该函数作为 `axis.x.labelFormatter`；Tooltip 和表格渲染链路不接入。

**Tech Stack:** Vue 3、TypeScript 5.7、AntV G2 5、Node.js `assert`、TypeScript `transpileModule`、Vite。

## Global Constraints

- 只修改图表坐标轴标签，不修改 SQL、接口、持久化配置或查询结果。
- 横轴日期显示 `MM/DD`；Tooltip 和明细表保留原始完整日期。
- 不依赖字段名猜测日期含义，不宽松解析普通分类值。
- 非日期字符串、数字、空值和非法日期保持现有字符串展示。
- 不修改 `g2-ssr`，本次仅覆盖浏览器内共享图表渲染链路。
- 使用中文注释和中文 Git 提交信息。
- 保留工作区内与本任务无关的未跟踪文件和用户改动。

---

## File Map

- `frontend/src/views/chat/component/charts/utils.ts`：提供严格日期识别与横轴短标签纯函数，并让混合单位图表复用。
- `frontend/src/views/chat/component/charts/axis-date-label.test.mjs`：执行纯函数行为测试和图表接入契约测试。
- `frontend/src/views/chat/component/charts/{Line,Area,Column,Bar,Scatter,Heatmap}.ts`：为各自横轴配置接入共享格式化函数。

### Task 1: 日期轴标签纯函数

**Files:**
- Modify: `frontend/src/views/chat/component/charts/utils.ts:61`
- Create: `frontend/src/views/chat/component/charts/axis-date-label.test.mjs`

**Interfaces:**
- Consumes: G2 传入的任意横轴刻度值 `value: unknown`。
- Produces: `formatCategoryAxisLabel(value: unknown): string`，日期返回 `MM/DD`，其他值返回现有字符串表示。

- [ ] **Step 1: 写失败的纯函数行为测试**

创建 `frontend/src/views/chat/component/charts/axis-date-label.test.mjs`。测试从当前源码提取单个自包含函数，经 TypeScript 转译后执行，避免加载 `utils.ts` 中的路径别名依赖：

```javascript
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import ts from 'typescript'

const utilsSource = readFileSync('src/views/chat/component/charts/utils.ts', 'utf8')
const functionMatch = utilsSource.match(
  /const ISO_DATE_AXIS_VALUE_PATTERN[\s\S]*?^\}/m
)

assert.ok(functionMatch, '图表工具层必须提供共享日期轴标签格式化函数')

const compiled = ts.transpileModule(functionMatch[0], {
  compilerOptions: {
    module: ts.ModuleKind.ESNext,
    target: ts.ScriptTarget.ES2022,
  },
}).outputText
const moduleUrl = `data:text/javascript;base64,${Buffer.from(compiled).toString('base64')}`
const { formatCategoryAxisLabel } = await import(moduleUrl)

assert.equal(formatCategoryAxisLabel('2026-07-27'), '07/27')
assert.equal(formatCategoryAxisLabel('2026-07-27 08:30:00'), '07/27')
assert.equal(formatCategoryAxisLabel('2026-07-27T08:30:00Z'), '07/27')
assert.equal(formatCategoryAxisLabel('2026-02-29'), '2026-02-29')
assert.equal(formatCategoryAxisLabel('2024-02-29'), '02/29')
assert.equal(formatCategoryAxisLabel('2026-13-01'), '2026-13-01')
assert.equal(formatCategoryAxisLabel('release-2026-07-27'), 'release-2026-07-27')
assert.equal(formatCategoryAxisLabel(20260727), '20260727')
assert.equal(formatCategoryAxisLabel(null), '')
assert.equal(formatCategoryAxisLabel(undefined), '')
```

- [ ] **Step 2: 运行测试并确认失败**

Run from `frontend`:

```powershell
node src/views/chat/component/charts/axis-date-label.test.mjs
```

Expected: FAIL，提示“图表工具层必须提供共享日期轴标签格式化函数”。

- [ ] **Step 3: 实现最小纯函数**

在 `formatNumber` 前增加：

```typescript
const ISO_DATE_AXIS_VALUE_PATTERN =
  /^(\d{4})-(\d{2})-(\d{2})(?:$|[ T]\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?(?:Z|[+-]\d{2}:?\d{2})?)$/

export function formatCategoryAxisLabel(value: unknown): string {
  if (value === null || value === undefined) {
    return ''
  }

  const text = String(value)
  const match = text.match(ISO_DATE_AXIS_VALUE_PATTERN)
  if (!match) {
    return text
  }

  const year = Number(match[1])
  const month = Number(match[2])
  const day = Number(match[3])
  const date = new Date(Date.UTC(year, month - 1, day))
  if (
    date.getUTCFullYear() !== year ||
    date.getUTCMonth() !== month - 1 ||
    date.getUTCDate() !== day
  ) {
    return text
  }

  return `${match[2]}/${match[3]}`
}
```

- [ ] **Step 4: 运行纯函数测试并确认通过**

Run from `frontend`:

```powershell
node src/views/chat/component/charts/axis-date-label.test.mjs
```

Expected: PASS，退出码为 0。

- [ ] **Step 5: 提交纯函数与行为测试**

```powershell
git add -- frontend/src/views/chat/component/charts/utils.ts frontend/src/views/chat/component/charts/axis-date-label.test.mjs
git commit -m "功能：增加图表日期轴短格式"
```

### Task 2: 非明细图表统一接入

**Files:**
- Modify: `frontend/src/views/chat/component/charts/axis-date-label.test.mjs`
- Modify: `frontend/src/views/chat/component/charts/utils.ts:512`
- Modify: `frontend/src/views/chat/component/charts/Line.ts:4`
- Modify: `frontend/src/views/chat/component/charts/Area.ts:4`
- Modify: `frontend/src/views/chat/component/charts/Column.ts:4`
- Modify: `frontend/src/views/chat/component/charts/Bar.ts:4`
- Modify: `frontend/src/views/chat/component/charts/Scatter.ts:4`
- Modify: `frontend/src/views/chat/component/charts/Heatmap.ts:4`

**Interfaces:**
- Consumes: Task 1 的 `formatCategoryAxisLabel(value: unknown): string`。
- Produces: 所有浏览器内 G2 横轴配置都使用 `labelFormatter: formatCategoryAxisLabel`。

- [ ] **Step 1: 增加失败的图表接入契约测试**

在 `axis-date-label.test.mjs` 末尾增加：

```javascript
const chartFiles = ['Line.ts', 'Area.ts', 'Column.ts', 'Bar.ts', 'Scatter.ts', 'Heatmap.ts']
for (const file of chartFiles) {
  const source = readFileSync(`src/views/chat/component/charts/${file}`, 'utf8')
  assert.match(
    source,
    /formatCategoryAxisLabel/,
    `${file} 必须复用共享日期轴标签格式化函数`
  )
  assert.match(
    source,
    /axis:\s*\{[\s\S]*?x:\s*\{[\s\S]*?labelFormatter:\s*formatCategoryAxisLabel/,
    `${file} 的横轴必须使用共享日期格式`
  )
}

assert.match(
  utilsSource,
  /function buildMixedUnitComboOptions[\s\S]*?const xAxisOptions = \{[\s\S]*?labelFormatter:\s*formatCategoryAxisLabel/,
  '混合单位图表横轴必须使用共享日期格式'
)

const tableSource = readFileSync('src/views/chat/component/charts/Table.ts', 'utf8')
assert.doesNotMatch(
  tableSource,
  /formatCategoryAxisLabel/,
  '明细表不得接入日期轴短格式'
)
```

- [ ] **Step 2: 运行测试并确认接入断言失败**

Run from `frontend`:

```powershell
node src/views/chat/component/charts/axis-date-label.test.mjs
```

Expected: FAIL，首先指出 `Line.ts` 尚未复用共享函数。

- [ ] **Step 3: 为所有横轴接入共享函数**

在六个图表文件现有的 `charts/utils.ts` 导入列表中加入：

```typescript
formatCategoryAxisLabel,
```

在每个文件的 `axis.x` 配置中加入：

```typescript
labelFormatter: formatCategoryAxisLabel,
```

在 `buildMixedUnitComboOptions()` 的 `xAxisOptions` 中加入同一配置：

```typescript
const xAxisOptions = {
  title: false,
  labelFontSize: 11,
  labelFormatter: formatCategoryAxisLabel,
  labelAutoHide: {
    type: 'hide',
    keepHeader: true,
    keepTail: true,
  },
  labelAutoRotate: false,
  labelAutoWrap: true,
  labelAutoEllipsis: true,
}
```

不得修改任何 `tooltip` 回调，也不得修改 `Table.ts`。

- [ ] **Step 4: 运行目标测试和现有图表回归**

Run from `frontend`:

```powershell
node src/views/chat/component/charts/axis-date-label.test.mjs
node src/views/chat/component/ChartComponent.resize.test.mjs
node src/views/chat/component/Table.null-display.test.mjs
```

Expected: 三个命令全部 PASS，退出码均为 0。

- [ ] **Step 5: 运行 TypeScript 与生产构建验证**

Run from `frontend`:

```powershell
npm run build
```

Expected: `vue-tsc -b` 与 `vite build` 均成功，退出码为 0。

- [ ] **Step 6: 检查变更范围并提交接入改动**

```powershell
git diff --check
git status --short
git add -- frontend/src/views/chat/component/charts/utils.ts frontend/src/views/chat/component/charts/axis-date-label.test.mjs frontend/src/views/chat/component/charts/Line.ts frontend/src/views/chat/component/charts/Area.ts frontend/src/views/chat/component/charts/Column.ts frontend/src/views/chat/component/charts/Bar.ts frontend/src/views/chat/component/charts/Scatter.ts frontend/src/views/chat/component/charts/Heatmap.ts
git diff --cached --check
git commit -m "功能：统一非明细图表日期轴展示"
```

Expected: 只提交本任务图表文件；不暂存现有未跟踪的日期筛选计划或其他用户改动。

## Final Verification

- [ ] 从 `frontend` 再运行 `node src/views/chat/component/charts/axis-date-label.test.mjs`。
- [ ] 从 `frontend` 再运行 `npm run build`。
- [ ] 检查 `git diff --check` 和 `git status --short`，确认没有生成产物或意外改动。
- [ ] 本地服务可用时，在看板确认日期横轴显示 `07/27`，Tooltip 显示完整日期，明细表不变。
