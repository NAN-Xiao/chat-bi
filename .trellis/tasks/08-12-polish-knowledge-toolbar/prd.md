# 优化知识库管理页工具栏布局

## Goal

重新组织知识库管理页标题、筛选和操作按钮布局，修复宽屏下输入控件被拉伸及按钮错行造成的视觉问题。

## Requirements

- 保留现有搜索、范围筛选、刷新、检索预览、模板下载和新建知识库功能及权限逻辑。
- 桌面端将标题说明与工具栏清晰分区，搜索框和范围筛选保持稳定宽度，操作按钮保持紧凑对齐，不再出现输入控件横跨整行、按钮单独掉到下一行的布局。
- 中等宽度允许工具栏分组换行，小屏幕改为适合触控的纵向/网格布局。
- 不引入横向页面滚动，表格仍紧接在工具栏下方。

## Acceptance Criteria

- [x] 典型桌面视口下，筛选控件与操作按钮位于同一条工具栏且无异常拉伸或孤立换行。
- [x] 980px 以下标题与工具栏自然堆叠，680px 以下筛选控件占满可用宽度，按钮区域可读可操作。
- [x] 原有按钮、下拉菜单、事件处理与权限条件保持不变。
- [x] 前端构建和知识库模板相关测试通过。
- [x] 在真实页面检查桌面与移动视口，无页面级横向溢出，并保存截图人工确认。

## Notes

- Keep `prd.md` focused on requirements, constraints, and acceptance criteria.
- Lightweight tasks can remain PRD-only.
- For complex tasks, add `design.md` for technical design and `implement.md` for execution planning before `task.py start`.

## Implementation Log

- 将 `KnowledgeBaseV2Panel.vue` 的工具栏拆分为筛选组和按钮组，为筛选控件添加稳定宽度类，并增加轻量容器边界。
- 桌面端保持单行紧凑布局；1440px 以下标题与工具栏分层；680px 以下筛选项纵向铺满，按钮使用两列网格。
- 更新 `knowledgeMarkdownTemplates.test.ts`，校验分组结构、稳定宽度和响应式规则。

## Verification Log

- `node --test tests/knowledgeMarkdownTemplates.test.ts`：3/3 通过。
- `npm run build`：通过（`vue-tsc -b` 与 Vite production build）。
- 定向 ESLint（关闭该旧组件全文件已有的 Prettier/CRLF 格式规则）通过，无 error 或 warning；未做无关的整文件格式化。
- 浏览器 1280×720：工具栏宽 992px，`scrollWidth = clientWidth = 990`，筛选框 220px/150px，四个操作按钮同排。
- 浏览器 680×820：筛选控件铺满，操作按钮为两列；页面 `scrollWidth = clientWidth = 680`，工具栏无内部溢出。
- 视觉验证时仅临时强制渲染 V2 组件，验证后已恢复；未改变页面模式判断逻辑。
