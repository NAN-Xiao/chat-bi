# 智能问数权限错误展示实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让图表数据接口返回权限失败时，智能问数页面通过统一错误组件展示“没有查看权限”。

**Architecture:** 在现有 `applyChartDataResponseToRecord` 边界统一映射结构化失败响应，保留原始 `record.data`，同时维护 `record.error`。所有加载路径继续复用该函数，不改后端协议和组件结构。

**Tech Stack:** Vue 3、TypeScript、Node.js `assert`、esbuild

## Global Constraints

- 核心行为必须保持数据源与业务领域无关。
- 不增加静默字段回退或业务表名硬编码。
- 先验证失败测试，再写最小实现。

---

### Task 1: 归一化图表数据失败状态

**Files:**
- Modify: `frontend/src/views/chat/answer/chartDataResponse.ts`
- Modify: `frontend/src/views/chat/answer/ChartAnswer.vue`
- Test: `frontend/tests/chat-chart-data-response.test.mjs`

**Interfaces:**
- Consumes: `applyChartDataResponseToRecord(record: any, response: any)` 的现有调用方式。
- Produces: 同一函数在 `response.status === 'failed'` 时设置 `record.error`，在非失败响应时清除旧错误；错误状态不挂载图表块。

- [ ] **Step 1: 写失败回归测试**

在现有测试中增加权限失败断言：响应和 `error_type` 保留在 `record.data`，`record.error` 等于后端消息；让已有成功响应记录预置旧错误，断言成功后错误被清除；并断言 `ChartBlock` 在记录存在错误时不挂载。

- [ ] **Step 2: 运行测试并确认按预期失败**

Run: `node tests/chat-chart-data-response.test.mjs`

Expected: FAIL，因为权限失败后 `record.error` 仍为 `undefined`、成功后旧错误未清除，或错误状态仍会挂载图表块。

- [ ] **Step 3: 写最小实现**

在保存 `record.data` 后处理 `status === 'failed'`：优先使用非空 `message`，其次使用非空 `reason`；`permission_denied` 无消息时使用“没有查看权限”，其他失败使用通用错误提示。非失败响应把 `record.error` 设为 `undefined`，然后保持既有 `business_notice` 分支。在 `ChartAnswer.vue` 中让 `ChartBlock` 仅在记录没有错误时挂载。

- [ ] **Step 4: 运行聚焦测试并确认通过**

Run: `node tests/chat-chart-data-response.test.mjs`

Expected: 输出 `chat chart data response tests passed`，退出码为 0。

- [ ] **Step 5: 运行前端构建验证**

Run: `npm run build`

Expected: TypeScript 检查和 Vite 构建均成功，退出码为 0。
