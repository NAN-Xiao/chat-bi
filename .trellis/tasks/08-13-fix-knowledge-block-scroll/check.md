# 检查记录

## 根因

桌面端知识块目录没有独立的纵向滚动约束。长列表会撑高两列网格和抽屉正文；外层抽屉滚到后半段目录项时，网格顶部的单个详情区已离开视口，因此用户只能看到左侧目录和右侧空白区域。

## 修复

- 两列网格使用顶部对齐。
- 桌面目录使用视口相关最大高度、独立纵向滚动和滚动边界隔离。
- `680px` 及以下显式取消桌面高度约束，保持横向目录且隐藏纵向溢出。
- 回归测试同时约束桌面滚动职责和移动端覆盖规则。

## 自动检查

- `node --test src/views/knowledge-base/DocumentEditor.layout.test.mjs`：7/7 通过。
- `npm run build`：通过，包含 `vue-tsc -b` 和 Vite 生产构建；仅保留仓库既有打包警告。
- `npx eslint ... --rule "prettier/prettier: off"`：通过，无语义 lint 问题。
- 完整 ESLint 的 `prettier/prettier` 规则会要求整体重排两个历史紧凑格式文件；为避免与修复无关的大面积格式差异，本任务未自动重排。
- `git diff --check`：通过。

## 浏览器检查

- 使用真实 `DocumentEditor.vue` 和 70 个内存知识块在隔离 Vite 端口验证，未调用或修改后端业务数据。
- 桌面 `1280x720`：目录 `clientHeight=540`、`scrollHeight=2450`、`overflow-y=auto`；点击第 56 项后目录 `scrollTop=1673`，详情 `top=57` 且标题为 `事件：EventName56`，文档滚动和横向溢出均为 0。
- 移动 `390x844`：目录 `overflow-x=auto`、`overflow-y=hidden`、`max-height=none`，详情位于目录下方，页面横向溢出为 0。
- 截图：`.codex-runtime/screenshots/knowledge-block-scroll-desktop.png`、`.codex-runtime/screenshots/knowledge-block-scroll-mobile.png`。

## 运行环境说明

真实平台管理员登录已成功，但当前已有 `8000` 后端对新版 `GET /api/v1/knowledge-base/capabilities` 返回 `405`，表明正在运行的后端版本与本 worktree 前端不一致。未重启或替换用户现有后端；组件布局改用同一 Vite 编译链的隔离预览完成验证。

## Bug 复盘

- 分类：D（测试覆盖缺口）+ E（隐含假设）。原实现隐含假设“两列网格的自然高度不会超过抽屉视口”，而源码级布局测试只检查结构存在，无法验证浏览器实际滚动元素。
- 为什么容易漏检：只断言 `overflow-y: auto` 能产生假阳性；必须用足够长的数据让 `scrollHeight > clientHeight`，并实际点击初始视口外的目录项。
- 防复发：回归测试约束桌面和移动 CSS 合同；浏览器质量门禁额外断言深层选择后目录 `scrollTop` 增加、详情仍在视口、外层抽屉/页面滚动不变。
- 系统性范围：同类“目录 + 单详情”双栏编辑器均应遵守同一滚动职责，不应把长目录交给页面或抽屉正文滚动。
- 知识沉淀：已更新 `.trellis/spec/frontend/project-runtime.md`。
