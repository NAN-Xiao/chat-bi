# formatArg 大小写布尔值修复实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 `formatArg` 正确解析大小写混合和带空白的布尔配置值，同时保持数字与普通文本的既有行为。

**Architecture:** 将无依赖的参数解析函数拆到独立 TypeScript 模块，原 `utils.ts` 重新导出同名 API，现有调用方不变。使用 Node 24 内置测试运行器直接执行纯 TypeScript 回归测试，不新增前端测试依赖。

**Tech Stack:** TypeScript、Node.js 24 `node:test`、Vite/Vue 构建链路

## Global Constraints

- 不修改 `formatArg` 的调用方。
- `"1"` 和 `"0"` 保持返回数字 `1` 和 `0`。
- 非布尔类普通文本保持原样返回。
- 不引入新的 npm 依赖。

---

### Task 1: 修复 formatArg 大小写解析

**Files:**
- Create: `frontend/src/utils/formatArg.ts`
- Create: `frontend/tests/formatArg.test.ts`
- Modify: `frontend/src/utils/utils.ts:296`

**Interfaces:**
- Produces: `formatArg(text: string)`
- Preserves: `@/utils/utils` 继续导出 `formatArg`

- [x] **Step 1: 写入失败回归测试**

覆盖 `False`、`TRUE`、首尾空白、数字字符串、普通文本和空字符串。

- [x] **Step 2: 运行测试确认红灯**

Run: `npm run test:format-arg`（工作目录 `frontend`）

Expected: `False` 或空白大小写用例失败，证明测试复现当前缺陷。

- [x] **Step 3: 写入最小实现**

对输入执行 `trim().toLowerCase()`，仅对 `true`、`false`、`1`、`0` 调用 `JSON.parse`；其他文本返回原值，并由 `utils.ts` 重新导出。

- [x] **Step 4: 运行测试确认绿灯**

Run: `npm run test:format-arg`（工作目录 `frontend`）

Expected: 全部用例通过，无警告。

- [x] **Step 5: 验证前端构建与浏览器配置加载**

Run: `npm run build`（工作目录 `frontend`）

Expected: TypeScript 检查和 Vite 构建成功；浏览器进入 AI 看板时不再出现 `"False" is not valid JSON`。
