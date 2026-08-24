# 完整关闭事件 value_mappings AI 通道

## Goal

完整关闭工作空间 tracking 字段 `value_mappings` 进入 AI 上下文的通道，避免模型通过 `m-schema`、`<Workspace-Tracking-Rules>` 或字段召回逻辑继续读取、列举或选择其中的事件值。配置数据继续保留给管理和目录能力使用。

## Background

- 已完成的“关闭工作空间事件字典 AI 通道”只清除了 `event_name_mappings`、`event_groups`、事件默认字段和请求级事件属性投影。
- `backend/apps/datasource/crud/datasource.py:1070` 的 `_dictionary_field_comment()` 仍将字段级 `value_mappings` 拼入 AI schema 字段注释。
- `backend/apps/system/crud/tracking_config.py:984` 的字段匹配文本和 `:1032` 的 Tracking Prompt 字段渲染仍读取 `value_mappings`。
- `backend/apps/knowledge_base/source_references.py:67` 仍从原始 tracking 配置生成结构化事件与 JSON 字段记录，并由统一语义上下文注入模型，形成第三条旁路。
- 用户截图证明 `event.event.value_mappings` 中的事件列表仍可被模型读取，属于共享 AI 上下文旁路，而不是缓存或物理 schema 枚举。

## Requirements

- 所有工作空间 tracking 字段的 `value_mappings` 不得序列化进入 AI 使用的 `m-schema` 字段注释。
- 所有工作空间 tracking 字段的 `value_mappings` 不得序列化进入 `<Workspace-Tracking-Rules>` 或其 summary。
- tracking 结构化知识适配器必须使用同一 AI-safe 投影：不得输出事件字典记录，JSON 字段记录可保留但其 `value_mappings` 必须为空。
- `value_mappings` 不得参与按用户问题匹配 tracking 字段，防止被禁用内容继续影响 AI 字段选择。
- 关闭策略必须位于共享 AI 上下文组装层，对 Smart Q&A、分析助手、普通聊天、AI 看板和共享 SQL Engine 一致生效，不增加入口专用分支。
- 保留 `value_mappings` 的数据库字段、管理 API、事件目录、Schema 管理接口、Excel 导入导出和前端数据字典展示/维护能力。
- 不删除或清洗管理员已保存的数据，不增加物理表扫描、相似字段替换或其他静默回退。
- `aliases`、`example_values`、字段说明、字段角色、JSON Path、表达式、SQL 规则等非 `value_mappings` 元数据不在本次关闭范围内。

## Acceptance Criteria

- [x] 带有 `value_mappings` 的普通字段和事件名字段生成 AI schema 时，输出均不包含 `value_mappings=`，也不包含其中的示例值。
- [x] 同一配置生成 `<Workspace-Tracking-Rules>` 时，正文和 summary 均不包含 `value_mappings=` 或其中的示例值。
- [x] 同一配置生成统一结构化语义上下文时，不包含 tracking 事件记录；保留的 JSON 字段记录不携带 `value_mappings`，且原始管理配置不被修改。
- [x] 仅在 `value_mappings` 中命中用户问题的字段不会因此进入 tracking 字段投影；默认字段及通过字段名、注释、Data Skill 命中的字段仍按现有规则处理。
- [x] Schema 管理/数据字典 API 仍返回原始 `value_mappings`，证明非 AI 管理能力未被删除。
- [x] Smart Q&A 等共享业务 SQL 上下文调用方无需各自修改即可获得一致关闭行为。
- [x] 定向后端测试、Ruff、Python 编译和 `git diff --check` 通过。

## Out Of Scope

- 删除 `value_mappings` 的持久化字段、历史记录或管理界面。
- 禁止用户问题、Data Skill、知识库正文、字段说明或其他独立语义来源显式提及事件名。
- 修改事件权限、SQL 安全校验、事件目录查询或业务指标口径。

## Risks

- 依赖字段枚举映射才能理解业务值的问题将不再自动获得这些映射；如仍需提供，应通过 Data Skill、知识库或明确字段说明等独立受控语义来源配置。
- 必须覆盖 AI schema 和 Tracking Prompt 两条共享链路，否则相同现象会从另一入口复发。
