# 修复知识库编辑器知识块列表滚动

## Goal

让知识块目录独立纵向滚动，避免右侧详情被页面滚动带走；保持移动端横向滚动。

## Requirements

- 桌面端知识块目录使用独立的纵向滚动容器，长列表不能继续撑高右侧详情区域或编辑抽屉。
- 右侧当前知识块详情保持静态布局，不新增独立滚动条或隐藏现有内容。
- 移动端目录继续使用横向滚动，并关闭桌面端纵向滚动约束。
- 为桌面端和移动端滚动行为增加布局回归断言。

## Acceptance Criteria

- [ ] 桌面端 `.block-directory` 有视口相关最大高度、`overflow-y: auto` 和滚动边界隔离。
- [ ] `.block-workspace` 顶部对齐，右侧详情不会被左侧目录高度拉伸。
- [ ] 移动端 `.block-directory` 恢复无最大高度、仅横向滚动且关闭纵向滚动。
- [ ] 相关布局测试通过，前端构建通过。

## Notes

- Keep `prd.md` focused on requirements, constraints, and acceptance criteria.
- Lightweight tasks can remain PRD-only.
- For complex tasks, add `design.md` for technical design and `implement.md` for execution planning before `task.py start`.
