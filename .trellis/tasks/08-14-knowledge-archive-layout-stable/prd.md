# 知识库当前与已归档切换布局稳定

## Goal

保持当前知识与已归档切换时顶部工具栏、表格列和详情布局稳定，并移除截图所示左侧空白占位。

## Requirements

- “当前知识”和“已归档”切换时，顶部筛选与操作区域的位置、宽度和高度保持一致。
- “当前知识”和“已归档”切换时，知识库表格的列结构和列宽保持一致。
- 已归档视图不应暴露检索预览、模板下载、新建知识库或参与检索操作，但隐藏这些操作时必须保留布局占位。
- 移除知识库面板左侧重复的标题/说明区域及其固定宽度占位，让顶部操作栏使用完整可用宽度。
- 保持现有权限边界、归档恢复行为、列表查询参数和移动端响应式能力不变。

## Acceptance Criteria

- [ ] 在桌面宽度下反复切换“当前知识”和“已归档”，顶部控件不横向移动、不换行抖动。
- [ ] 两种视图的表格列标题和列宽一致；已归档记录的“参与检索”显示为不可操作状态。
- [ ] 已归档视图中不适用的操作不可见、不可聚焦、不可点击，但对应空间仍被保留。
- [ ] 页面不再渲染“知识库管理”和说明文字组成的左侧标题块，也不保留其空白宽度。
- [ ] 相关前端布局测试、生产构建和浏览器桌面/移动端检查通过，页面无新增横向溢出。

## Notes

- Keep `prd.md` focused on requirements, constraints, and acceptance criteria.
- Lightweight tasks can remain PRD-only.
- For complex tasks, add `design.md` for technical design and `implement.md` for execution planning before `task.py start`.
