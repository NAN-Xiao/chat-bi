# 修复知识块删除确认框被遮挡

## Goal

让知识库编辑抽屉内的知识块删除确认框真实可见、可操作，并在确认后明确反馈草稿状态变化。

## Requirements

- 删除按钮使用与编辑抽屉一致的 UI 弹层实现，避免不同组件库的独立 z-index 管理造成遮挡。
- 保持删除只修改本地草稿、保存草稿后落库的现有语义。
- 取消删除、只剩一个知识块和只读模式的既有行为保持不变。

## Acceptance Criteria

- [x] 在真实 2.0 页面点击删除图标后，确认框显示在编辑抽屉上方。
- [x] 新增一个未保存临时知识块并确认删除后，知识块数量恢复且显示“知识块已删除，请保存草稿”。
- [x] 不保存临时测试数据，不删除既有业务知识块。
- [x] 聚焦测试、定向 ESLint 和前端构建通过。

## Root Cause Evidence

- 浏览器点击后 DOM 中存在 `.el-overlay-message-box`，但截图中确认框不可见。
- 编辑抽屉由 `element-plus-secondary` 渲染为 `.ed-drawer`，而 `DocumentEditor.vue` 单独从 `element-plus` 导入 `ElMessageBox`，两套弹层各自维护 z-index。
- 仓库内处于抽屉/管理页面的显式 MessageBox 导入统一使用 `element-plus-secondary`。

## Out Of Scope

- 不改变后端知识块结构 API、保存草稿流程或冲突协议。
- 不删除或保存现有业务知识内容。

## Goal

知识块删除确认框已创建但被编辑抽屉遮挡，需统一弹层实现并完成真实点击验证。

## Requirements

- TBD

## Acceptance Criteria

- [ ] TBD

## Notes

- Keep `prd.md` focused on requirements, constraints, and acceptance criteria.
- Lightweight tasks can remain PRD-only.
- For complex tasks, add `design.md` for technical design and `implement.md` for execution planning before `task.py start`.
