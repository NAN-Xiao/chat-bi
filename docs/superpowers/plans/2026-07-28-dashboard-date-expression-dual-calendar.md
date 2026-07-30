# 看板日期表达式双月日历实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在日期表达式弹层右侧补齐可交互的双月日期范围面板，并让日历选区转换为静态自定义时间表达式。

**Architecture:** 组件内部继续以 `draft` 作为唯一编辑态，新增一个由 `preview` 派生的日历范围计算属性；快捷预设只改变表达式并同步日历高亮，日历完整选区则写入两个静态端点。复用 Element Plus `ElDatePickerPanel` 和中文 locale，不修改旧 `sq-view` 日期面板及既有 SQL 刷新链。

**Tech Stack:** Vue 3 Composition API、TypeScript、Element Plus 2.10、Node.js 契约测试、Vite。

## Global Constraints

- 只修改 `DashboardDateExpressionPicker.vue`、其契约测试和本计划的验证状态。
- 不修改 `frontend/src/views/dashboard/components/sq-view/index.vue`。
- 不增加 ROI 名称、看板 ID、数据源或业务字段运行时分支。
- 快捷预设保持 `preset` 语义；只有日历直接选区才转换为两个静态端点。
- 点击“应用”前不得更新外部模型；取消或关闭继续丢弃草稿。
- 使用现有 Element Plus 依赖，不增加新包。

---

### Task 1: 双月日历契约与交互实现

**Files:**
- Modify: `frontend/src/views/dashboard/common/DashboardDateExpressionPicker.test.mjs`
- Modify: `frontend/src/views/dashboard/common/DashboardDateExpressionPicker.vue`

**Interfaces:**
- Consumes: `preview: ComputedRef<{ start: string; end: string }>` 和现有 `draft: Ref<DashboardDateExpression>`。
- Produces: `calendarRange` 双向计算属性与 `updateCalendarRange(value)`，完整选区生成 `mode: 'range'` 的两个静态端点。

- [ ] **Step 1: 写入失败的组件契约测试**

在 `DashboardDateExpressionPicker.test.mjs` 增加以下断言：

```js
assert.match(source, /import\s*{[\s\S]*ElConfigProvider[\s\S]*ElDatePickerPanel[\s\S]*}\s*from\s*'element-plus'/)
assert.match(source, /import elementZhCnLocale from 'element-plus\/es\/locale\/lang\/zh-cn'/)
assert.match(source, /import 'element-plus\/es\/components\/date-picker-panel\/style\/css'/)
assert.match(source, /const calendarRange = computed/)
assert.match(source, /function updateCalendarRange/)
assert.match(source, /start:\s*{\s*mode:\s*'static',\s*date:\s*start\s*}/)
assert.match(source, /end:\s*{\s*mode:\s*'static',\s*date:\s*end\s*}/)
assert.match(source, /<ElConfigProvider :locale="elementZhCnLocale">[\s\S]*<ElDatePickerPanel/)
assert.match(source, /<ElDatePickerPanel[\s\S]*v-model="calendarRange"/)
assert.match(source, /type="daterange"/)
assert.match(source, /value-format="YYYY-MM-DD"/)
assert.match(source, /unlink-panels/)
```

- [ ] **Step 2: 运行测试确认 RED**

Run: `cd frontend; node src/views/dashboard/common/DashboardDateExpressionPicker.test.mjs`

Expected: FAIL，首个失败为缺少 `ElConfigProvider`/`ElDatePickerPanel` 导入。

- [ ] **Step 3: 增加日历数据适配与静态范围转换**

在组件脚本中导入面板、样式和中文 locale，并增加：

```ts
type CalendarRange = [string, string] | []

function updateCalendarRange(value: CalendarRange | null) {
  if (!Array.isArray(value) || value.length !== 2) return
  const [start, end] = value
  if (!start || !end) return
  draft.value = {
    version: 1,
    mode: 'range',
    start: { mode: 'static', date: start },
    end: { mode: 'static', date: end },
  }
}

const calendarRange = computed<CalendarRange>({
  get: () => draft.value.mode === 'preset' && draft.value.preset === 'all_time'
    ? []
    : [preview.value.start, preview.value.end],
  set: updateCalendarRange,
})
```

保持 `all_time` 原表达式不变，避免让日历跳转到公元 1000 年或 9999 年。

- [ ] **Step 4: 用双月面板重构右侧模板**

将右侧主体调整为“自定义端点辅助区 + 始终存在的日历区”：

```vue
<main class="range-editor">
  <div v-if="draft.mode === 'range'" class="endpoint-controls">
    <section v-for="side in (['start', 'end'] as const)" :key="side" class="endpoint-panel">
      <!-- 保留现有动态/静态端点控件 -->
    </section>
  </div>
  <div class="calendar-panel">
    <ElConfigProvider :locale="elementZhCnLocale">
      <ElDatePickerPanel
        v-model="calendarRange"
        type="daterange"
        value-format="YYYY-MM-DD"
        :border="false"
        :clearable="false"
        :show-footer="false"
        unlink-panels
      />
    </ElConfigProvider>
  </div>
</main>
```

移除预设模式下两张 `preset-endpoint` 摘要卡，顶部现有 `preview.start → preview.end` 继续承担摘要职责。

- [ ] **Step 5: 调整双月布局样式**

将 popover 宽度扩大到可容纳 `160px` 快捷栏和双月面板；`.range-editor` 改为纵向布局，`.endpoint-controls` 为两列，`.calendar-panel` 隐藏面板外溢并覆盖 Element Plus 面板边框。窄视口下把端点辅助区改为单列，同时保证底部按钮不重叠。

- [ ] **Step 6: 运行组件契约测试确认 GREEN**

Run: `cd frontend; node src/views/dashboard/common/DashboardDateExpressionPicker.test.mjs`

Expected: 输出 `dashboard date expression picker contract passed`。

- [ ] **Step 7: 提交组件实现**

```powershell
git add -- frontend/src/views/dashboard/common/DashboardDateExpressionPicker.vue frontend/src/views/dashboard/common/DashboardDateExpressionPicker.test.mjs
git commit -m "功能：补齐日期表达式双月日历"
```

### Task 2: 回归验证与视觉验收

**Files:**
- Verify only: `frontend/src/views/dashboard/common/dashboardDateExpression.test.mjs`
- Verify only: `frontend/src/views/dashboard/components/sq-view/index.date-filter.test.mjs`
- Verify only: `frontend/src/views/dashboard/components/sq-view/index.vue`

**Interfaces:**
- Consumes: Task 1 的 `calendarRange` 和现有 `applyDraft()`。
- Produces: 自动化、构建与本地浏览器验收证据。

- [ ] **Step 1: 运行日期表达式与看板入口回归测试**

Run:

```powershell
cd frontend
node src/views/dashboard/common/dashboardDateExpression.test.mjs
node src/views/dashboard/common/DashboardDateExpressionPicker.test.mjs
node src/views/dashboard/components/sq-view/index.date-filter.test.mjs
```

Expected: 三个命令全部退出码为 `0`，分别输出各自通过信息。

- [ ] **Step 2: 确认旧日期控件没有代码变化**

Run: `git diff HEAD~1 -- frontend/src/views/dashboard/components/sq-view/index.vue`

Expected: 无输出。

- [ ] **Step 3: 运行前端生产构建**

Run: `cd frontend; npm run build`

Expected: `vue-tsc -b` 与 `vite build` 均成功，命令退出码为 `0`。

- [ ] **Step 4: 重启并验证四个本地服务**

Run:

```powershell
.\tools\stack-local.ps1 -Action restart -BackendPorts 8000 -StartMcp -SkipDatabase -SkipRedis -SkipNginx
$frontendListener = Get-NetTCPConnection -LocalPort 5173 -State Listen -ErrorAction SilentlyContinue
if ($frontendListener) { Stop-Process -Id $frontendListener.OwningProcess -Force }
$workspaceRoot = (Resolve-Path '.').Path
$runtimeRoot = Join-Path $workspaceRoot '.codex-runtime'
Start-Process -FilePath 'C:\Windows\System32\cmd.exe' -WorkingDirectory (Join-Path $workspaceRoot 'frontend') -ArgumentList '/c','npm run dev' -RedirectStandardOutput (Join-Path $runtimeRoot 'frontend-5173.current.out.log') -RedirectStandardError (Join-Path $runtimeRoot 'frontend-5173.current.err.log') -WindowStyle Hidden
```

随后执行 `Get-NetTCPConnection -LocalPort 5173 -State Listen` 和 `tools/stack-local.ps1 -Action status -BackendPorts 8000 -StartMcp -SkipDatabase -SkipRedis -SkipNginx`，验证 `5173` 返回 `200`、API `8000` 返回 `401`、MCP `8001` 返回 `404`、Worker 使用当前工作区隔离队列，同时核对模型参数为 `120 900 1`。

- [ ] **Step 5: 浏览器验收双月交互**

打开本地目标看板并验证：默认快捷范围在双月面板高亮；左右月份可导航；日历选择完整范围后显示“自定义时间”；取消不刷新；应用后按选择范围刷新；弹层内没有空白板块、文字遮挡或底部按钮重叠。分别在桌面宽屏和窄视口截图检查。

- [ ] **Step 6: 检查最终工作树**

Run: `git status --short --branch`

Expected: 仅保留任务开始前已有的 `logs/dashboard_ai_sql_llm_outputs.jsonl` 修改，不出现未提交的任务文件。
