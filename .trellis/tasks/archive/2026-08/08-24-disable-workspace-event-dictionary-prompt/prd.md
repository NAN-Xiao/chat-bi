# 关闭工作空间事件字典 AI 通道

## Goal

停止把工作空间事件字典作为 AI 生成 SQL 和回答的上下文来源，避免模型仅凭工作空间事件配置主动列举或选择事件。事件字典仍可由管理员维护，并继续服务于非 AI 的配置、导入、权限和目录展示能力。

## Background

- 当前 `build_tracking_prompt_context()` 会把已登记事件名、事件名映射和事件分组写入 `<Workspace-Tracking-Rules>`（`backend/apps/system/crud/tracking_config.py:1230`）。
- 当前 `_dictionary_schema_from_workspace()` 会调用 `project_event_schema_fields()`，把请求命中的事件属性追加到 `m-schema`（`backend/apps/datasource/crud/datasource.py:1176`、`:1333`）。
- 这两条链路使模型能够回答截图中的 `ShopBuyItem`、`ShopBuyComplete`，即使物理数据库 schema 已不再负责枚举事件。
- `find_tracking_prompt_context()` 被 Smart Q&A、普通聊天、分析助手和共享 SQL Engine 复用，因此必须在共享上下文层统一关闭，不能只改一个入口。

## Requirements

- AI Prompt 中不得再注入工作空间事件字典的事件名、事件名映射、事件分组或事件属性定义。
- `m-schema` 中不得再追加由工作空间事件字典生成的请求级事件属性 schema、事件谓词或 JSON 表达式。
- 保留工作空间中与事件字典无关的表说明、字段说明、字段角色、SQL 约束和工作空间说明；不得为了关闭事件字典而清空整个 `<Workspace-Tracking-Rules>`。
- 保留事件字典的数据库记录、管理 API、事件目录 API、Excel 导入导出、权限配置和前端维护能力。
- 所有复用共享业务 SQL 上下文的 AI 入口应用同一策略，不增加 Smart Q&A、分析助手或看板专用分支。
- 不从 Data Skill、知识库、用户问题或普通 schema 元数据中删除事件文字；这些独立来源如果显式包含事件名，仍可按各自规则进入上下文。
- 不增加兼容回退，不在事件字典通道关闭后从物理业务表、相似字段或其他数据源重新推断事件名。

## Acceptance Criteria

- [x] 给定包含 `ShopBuyItem`、`ShopBuyComplete` 的工作空间事件字典，AI tracking Prompt 不包含这两个事件名，也不包含 `<Configured-Event-Names>`、`## 事件名映射` 或 `## 事件分组`。
- [x] 同一配置生成的 `m-schema` 不包含 `【Request event attribute schema】`、`# Event:` 或事件字典派生的 `Required predicate`。
- [x] 同一工作空间配置中的非事件表/字段说明、SQL 约束和工作空间说明仍进入共享 AI 上下文。
- [x] Smart Q&A、普通聊天、分析助手、共享 SQL Engine/看板等调用方不再各自获得事件字典 AI 上下文。
- [x] 事件目录构建、配置保存和 Excel 导入导出的现有测试继续通过，证明管理数据未被删除或禁用。
- [x] 定向后端测试和受影响的 tracking/schema 测试通过；代码质量检查无新增错误。

## Out Of Scope

- 删除事件字典表、字段、API、权限类型或管理界面。
- 清理管理员已经维护的事件字典数据。
- 屏蔽用户问题、Data Skill、知识库或普通表/字段注释中显式出现的事件名。
- 修改事件指标口径、SQL 安全校验、知识检索 Top-K 或数据源权限逻辑。

## Risks

- 依赖事件字典才能生成 JSON 事件属性表达式的问题将不再自动获得这些表达式；模型应基于剩余的 Data Skill、知识或显式字段配置回答，缺失时明确说明配置不足。
- 当前部分 SQL 生成后校验复用了 tracking Prompt 文本。实现时必须避免因删除 Prompt 内容而触发新的物理事件表扫描或静默事件推断。
