# 看板图表渲染生命周期统一修复 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 统一看板编辑态和预览态的首次加载、原子绘制与尺寸重绘生命周期，消除数据就绪到图表首帧提交之间的加载圆环、白帧和重复 staging 闪烁。

**Architecture:** 看板卡片负责首次加载遮罩，图表组件在原子提交首个可见帧后发送 `render-ready`；卡片在首帧确认前让图表在遮罩后挂载，确认后保持 ready，后续后台刷新继续显示旧帧。编辑器与预览容器首次计算网格尺寸时不发送 `view-render-all`，只有挂载后的真实尺寸变化才合并广播一次。

**Tech Stack:** Vue 3、TypeScript、G2/S2、Node.js `node:test`/`assert`、Vite、Playwright

## Global Constraints

- 保留 `ChartComponent` 的隐藏 staging、异步完成后原子替换和独立内层 mount。
- 首次没有可见图表时由卡片完整遮罩覆盖渲染过程，不能在外层加载态和组件内部圆环之间切换。
- 已有可见帧后，刷新和尺寸重绘不得重新进入首次完整加载态。
- 初始网格尺寸必须在子图表挂载前就绪，但不能额外广播一次全量重绘。
- 挂载后的真实尺寸变化仍必须经过去重后广播一次。
- 不改业务数据、图表字段映射、数据源或看板持久化结构。

---

### Task 1: 固化首次渲染握手契约

**Files:**
- Modify: `frontend/src/views/chat/component/ChartComponent.atomic-render.test.mjs`
- Modify: `frontend/src/views/dashboard/components/sq-view/index.state-machine.test.mjs`

- [ ] 添加失败测试：`ChartComponent` 在 `commitStagedChart` 完成后发送 `render-ready`。
- [ ] 添加失败测试：卡片允许有数据的图表在首次完整遮罩后挂载，遮罩直到收到 `render-ready` 才消失。
- [ ] 添加失败测试：首帧 ready 后的后台刷新不重置 ready。
- [ ] 运行两个测试并确认 RED。

### Task 2: 统一卡片和图表首帧生命周期

**Files:**
- Modify: `frontend/src/views/chat/component/ChartComponent.vue`
- Modify: `frontend/src/views/dashboard/components/sq-view/index.vue`

- [ ] 在图表原子提交成功后发送 `render-ready`，每个组件实例的首个可见帧只需通知外层一次。
- [ ] 卡片维护当前图表实例的首帧 ready 状态，并在图表 key/身份真正变化时重置。
- [ ] 将“是否挂载图表”和“是否显示首次遮罩”拆开，先挂载后遮罩，避免数据 ready 后才开始绘图。
- [ ] 收到 `render-ready` 后移除首次遮罩；刷新期间保留可见图和 ready 状态。
- [ ] 移除组件内部延迟圆环作为正常首绘交接手段，确保加载态只有一个所有者。

### Task 3: 移除首次布局的冗余全量重绘

**Files:**
- Modify: `frontend/src/views/dashboard/editor/DashboardEditor.resize-lifecycle.test.mjs`
- Modify: `frontend/src/views/dashboard/preview/SQPreview.resize-observer.test.mjs`
- Modify: `frontend/src/views/dashboard/editor/DashboardEditor.vue`
- Modify: `frontend/src/views/dashboard/preview/SQPreview.vue`

- [ ] 添加失败测试：`sizeInit(true)` 只初始化网格，不调用 `scheduleViewRenderAll()`。
- [ ] 保留测试：挂载后的真实宽高变化仍调用一次去重广播。
- [ ] 运行测试并确认 RED。
- [ ] 为 `sizeInit` 增加明确的首次初始化/后续变化边界，并更新挂载调用。

### Task 4: 自动化回归与构建

**Files:**
- Verify only

- [ ] 运行图表原子渲染、尺寸、洞察布局、卡片状态机、响应式布局、预览 loading、编辑器和预览 resize 测试。
- [ ] 运行 `npm run build`。
- [ ] 运行 `git diff --check` 并检查最终差异只包含本次生命周期整理。

### Task 5: 编辑态与预览态浏览器验证

**Files:**
- Verify only

- [ ] 打开目标看板编辑态，记录 loading、active、staging、canvas 的时间线与控制台错误。
- [ ] 打开目标看板预览态执行同样验证。
- [ ] 确认首次遮罩无内部圆环交接、无白帧、无仅由初始布局广播触发的第二次 staging。
- [ ] 触发一次真实容器 resize，确认只发生一次隐藏 staging 到 active 的原子替换。
