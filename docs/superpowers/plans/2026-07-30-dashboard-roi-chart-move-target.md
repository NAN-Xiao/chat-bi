# Dashboard ROI Chart Move Target Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复 ROI 图表打开“移动到”弹窗时错误使用图表执行数据源查询目标看板的问题。

**Architecture:** 将移动目标数据源的解析收敛到 `dashboardOptions.ts` 的纯函数中，明确只读取看板归属数据源。`SQComponentWrapper.vue` 调用该函数加载目标看板树，现有图表复制、保存和 ROI 执行数据源校验流程保持不变。

**Tech Stack:** Vue 3、TypeScript、Node.js `assert` 测试、Vite、`vue-tsc`

## Global Constraints

- 目标看板列表只按照当前看板的有效归属数据源加载。
- 移动后的图表必须保留原有执行数据源，包括 ROI 数据源。
- 不修改后端 ROI 权限、绑定、SQL 执行或普通看板树权限。
- 看板缺少有效归属数据源时返回空目标列表，不使用图表数据源静默回退。
- 不修改或暂存工作区内其他未跟踪文件；未获明确要求时不提交或推送 Git。

---

### Task 1: 解析移动目标数据源并接入弹窗

**Files:**
- Modify: `frontend/src/views/dashboard/utils/dashboardOptions.ts`
- Modify: `frontend/src/views/dashboard/utils/dashboardOptions.test.mjs`
- Modify: `frontend/src/views/dashboard/preview/SQComponentWrapper.vue`

**Interfaces:**
- Consumes: 后端返回的 `dashboardInfo.datasource: string | number | null | undefined`
- Produces: `resolveDashboardMoveTargetDatasource(dashboardInfo): string | number | undefined`

- [x] **Step 1: 写入失败测试**

在 `dashboardOptions.test.mjs` 导入 `resolveDashboardMoveTargetDatasource`，并加入以下断言：

```js
assert.equal(
  resolveDashboardMoveTargetDatasource({ datasource: 3 }, { datasource: 7 }),
  3,
  'ROI 图表移动目标必须使用看板归属数据源'
)
assert.equal(
  resolveDashboardMoveTargetDatasource({ datasource: '3' }, { datasource: '3' }),
  '3',
  '普通图表移动目标应保持看板归属数据源'
)
assert.equal(
  resolveDashboardMoveTargetDatasource({ datasource: 3 }, { datasource: 7 }),
  3,
  '后端推导出的历史看板归属数据源应直接使用'
)
assert.equal(
  resolveDashboardMoveTargetDatasource({ datasource: null }, { datasource: 7 }),
  undefined,
  '看板缺少归属数据源时不得回退到图表执行数据源'
)
```

函数保留第二个参数用于测试证明图表执行数据源不会参与结果解析，但实现不得读取该参数。

- [x] **Step 2: 运行测试并确认按预期失败**

Run: `node frontend/src/views/dashboard/utils/dashboardOptions.test.mjs`

Expected: FAIL，错误指出 `resolveDashboardMoveTargetDatasource` 未导出或不是函数。

- [x] **Step 3: 实现最小纯函数**

在 `dashboardOptions.ts` 增加：

```ts
export function resolveDashboardMoveTargetDatasource(
  dashboardInfo?: Pick<SQTreeNode, 'datasource'> | null,
  _viewInfo?: Pick<SQTreeNode, 'datasource'> | null
): string | number | undefined {
  const datasource = dashboardInfo?.datasource
  return datasource === null || datasource === undefined || datasource === ''
    ? undefined
    : datasource
}
```

- [x] **Step 4: 接入移动弹窗**

在 `SQComponentWrapper.vue` 导入该函数，并把 `loadMoveTargets` 的数据源解析改为：

```ts
const datasourceId = resolveDashboardMoveTargetDatasource(
  props.dashboardInfo,
  currentViewInfo.value
)
```

其他移动、保存和回滚逻辑不变。

- [x] **Step 5: 运行聚焦测试并确认通过**

Run: `node frontend/src/views/dashboard/utils/dashboardOptions.test.mjs`

Expected: PASS，进程退出码为 `0`。

- [x] **Step 6: 运行前端类型检查与构建**

Run: `npm run build`

Working directory: `frontend`

Expected: `vue-tsc -b` 和 `vite build` 均成功，进程退出码为 `0`。

- [x] **Step 7: 检查最终差异**

Run: `git diff --check -- frontend/src/views/dashboard/utils/dashboardOptions.ts frontend/src/views/dashboard/utils/dashboardOptions.test.mjs frontend/src/views/dashboard/preview/SQComponentWrapper.vue`

Expected: 进程退出码为 `0`，且差异只包含纯函数、回归测试和组件调用替换。
