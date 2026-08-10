# 大文件拆分与通用能力提炼方案

## 1. 文档定位

- 评估日期：2026-08-10
- 适用范围：`backend/`、`frontend/src/`
- 文档类型：重构设计与分阶段实施方案
- 当前状态：方案阶段，尚未开始代码拆分

本文基于当前工作区代码扫描结果整理。目标是降低大文件的职责耦合、减少重复实现、提高测试可定位性，同时保持现有 API、权限边界、数据源上下文、图表配置和隐藏功能兼容。

本次不建议按行数机械拆分，也不建议一次性重写模块。拆分必须遵循“先稳定契约，再迁移实现，最后迁移调用方”的顺序。

## 2. 复核结论

当前超过 1000 行的源码文件大致为：

| 范围 | 数量 | 说明 |
| --- | ---: | --- |
| 后端 Python | 23 | 不包含虚拟环境、缓存目录和 Alembic 迁移目录 |
| 前端源码 | 25 | 包括 Vue、TypeScript、JavaScript 源码 |

真正需要优先拆分的文件，是同时包含状态管理、权限判断、数据转换、IO 调用和展示/编排逻辑的文件。

### 2.1 最高优先级

| 文件 | 行数 | 主要问题 | 优先级 |
| --- | ---: | --- | --- |
| `frontend/src/views/dashboard/common/DashboardSqlEditor.vue` | 6435 | SQL Builder、公式指标、日期参数、Pivot、MCP、预览合并、保存校验和模板全部集中 | P0 |
| `backend/apps/dashboard/crud/dashboard_service.py` | 5144 | 权限、资源树、Canvas、SQL/Pivot、缓存、模板、分享和 CRUD 混合 | P0 |
| `backend/apps/analysis_assistant/api/analysis_assistant.py` | 4179 | API、权限清理、会话、导出、时间策略、语义校验、图表选择和主流程混合 | P0 |
| `backend/apps/chat/task/smart_qa_graph.py` | 2334 | 事件可用性/SQL 重写与图节点编排混合 | P1 |
| `frontend/src/views/dashboard/components/sq-view/index.vue` | 3375 | 图表刷新、日期筛选、坐标轴、Pivot、导出、布局和展示混合 | P1 |
| `frontend/src/views/chat/component/ChartInsightHeader.vue` | 2001 | 趋势、漏斗、排名、统计计算和 DOM 适配混合 | P1 |

### 2.2 第二批

| 文件 | 行数 | 建议边界 |
| --- | ---: | --- |
| `frontend/src/views/dashboard/common/ResourceTree.vue` | 2111 | 树数据适配、展开状态、菜单权限、拖拽排序、资源操作 |
| `frontend/src/views/chat/index.vue` | 2016 | 聊天恢复、发送、流式回答、图表数据恢复、推荐问题 |
| `frontend/src/views/analysis-assistant/AnalysisAssistantDock.vue` | 2116 | Dock 交互、历史会话、SSE、导出、生成看板 |
| `backend/apps/system/crud/tracking_excel.py` | 2922 | Excel 导入、配置合并、Sheet 解析、导出和模板 |
| `backend/apps/system/api/tenant.py` | 3490 | 平台概览、租户概览、成员、申请、邀请、绑定和审计 |
| `backend/apps/chat/task/llm.py` | 2637 | `LLMService` 同时承担上下文、SQL、图表、执行、保存和任务生命周期 |
| `backend/apps/chat/curd/chat.py` | 2024 | 聊天 CRUD、历史投影、权限脱敏、图表数据、日志和答案保存 |
| `backend/apps/datasource/api/datasource.py` | 1947 | 数据源 CRUD、Schema、字段枚举、Excel/Schema 导入导出 |

### 2.3 暂不作为首批目标

- `backend/alembic/versions/*.py`：迁移文件应保持“一次迁移一个文件”，不应为了行数拆散历史迁移。
- 大型测试文件：应跟随生产模块拆分为按行为组织的测试文件，不应先单独重构测试结构。
- `frontend/src/views/login/index.vue`：模板、登录流程和样式体量较大，但对核心 BI 运行路径影响较低。
- `backend/apps/db/db.py`：确实偏大，但它是基础设施入口，拆分前必须先建立稳定的数据库连接、Schema、执行和方言接口。
- `backend/common/utils/utils.py`：不是最大文件，但已经有“通用工具袋”倾向；后续应按领域拆分，不能继续向其中追加业务逻辑。

## 3. 目标分层

拆分后的依赖方向建议保持如下结构：

```text
API / Vue 页面
    ↓
领域编排层 / composable
    ↓
领域服务与纯函数
    ↓
权限、数据源、数据库、缓存、任务队列等基础能力
```

约束如下：

1. API 层负责路由参数、依赖注入、响应格式和异常出口，不承载长业务流程。
2. Vue 页面负责模板、组件组合和事件转发，不直接实现完整的协议解析或复杂状态机。
3. 纯函数优先抽取到领域模块，只有跨领域且契约稳定的能力才放入 `common` 或 `src/utils`。
4. 权限判断不能因为拆分而变成通用的“万能权限函数”。租户、用户、数据源、表、字段和行权限仍需保留各自边界。
5. 不允许因抽取而增加静默字段替换、默认数据源替换或“取第一列”兼容逻辑。

## 4. 前端拆分设计

### 4.1 DashboardSqlEditor.vue

当前脚本区从约 208 行延伸到 4796 行，包含多组相对独立的逻辑。建议保留 `DashboardSqlEditor.vue` 作为对外兼容门面，先拆 composable 和子组件。

建议目录：

```text
frontend/src/views/dashboard/common/sql-editor/
├── SqlEditorSourcePanel.vue
├── SqlBuilderFilterPanel.vue
├── SqlBuilderMetricPanel.vue
├── SqlBuilderFormulaEditor.vue
├── SqlEditorPivotPanel.vue
├── SqlEditorMcpPanel.vue
├── SqlEditorPreviewPanel.vue
├── useSqlEditorState.ts
├── useSqlBuilderState.ts
├── useSqlBuilderValidation.ts
├── useSqlPreview.ts
├── useSqlPreviewMerge.ts
├── useMcpSource.ts
├── useExecutionDatasource.ts
└── sqlEditorTypes.ts
```

职责映射：

| 当前逻辑 | 目标模块 |
| --- | --- |
| `resetSqlBuilderState`、过滤器、指标、公式 Token | `useSqlBuilderState.ts`、`SqlBuilderMetricPanel.vue`、`SqlBuilderFormulaEditor.vue` |
| `collectLocalBuilderAgentAdvice`、`builderBlockingIssues` | `useSqlBuilderValidation.ts` |
| `runPreview`、结果快照、结果字段 | `useSqlPreview.ts` |
| `mergePreviewResults`、Join 字段和字段映射 | `useSqlPreviewMerge.ts` |
| `initInsightConfig`、`initForecastConfig`、`buildPivotConfig` | `chartConfig` 领域模块或对应 composable |
| MCP Schema、参数默认值、工具调用 | `useMcpSource.ts`、`SqlEditorMcpPanel.vue` |
| 执行数据源选择与清理 | `useExecutionDatasource.ts` |
| `writeEditorStateToViewInfo`、`builderConfigForSave` | `useSqlEditorState.ts`，保留原保存数据结构 |

第一阶段只抽纯函数和状态 composable，不改变模板层级。第二阶段再把明显独立的过滤器、公式、MCP、预览区域拆成 Vue 子组件。

### 4.2 SQView 与 ChartInsightHeader

`SQView` 应拆成“图表状态”和“展示组件”两部分：

```text
frontend/src/views/dashboard/components/sq-view/
├── index.vue
├── useSqViewState.ts
├── useSqViewDateFilter.ts
├── useSqViewPivot.ts
├── useSqViewRefresh.ts
├── SqViewChartFrame.vue
├── SqViewPivotToolbar.vue
└── SqViewTableExport.vue
```

`ChartInsightHeader.vue` 中的趋势、漏斗和排名计算应先抽成无 DOM 的纯函数：

```text
frontend/src/views/chat/component/chart-insight/
├── insightMetrics.ts
├── insightDate.ts
├── insightTrend.ts
├── insightFunnel.ts
├── insightRanking.ts
├── insightTypes.ts
└── ChartInsightHeader.vue
```

计算函数只接收 `ChartAxis`、数据行和配置，不能读取路由、DOM、数据源名称或 SLG 业务字段。

### 4.3 ResourceTree、Chat 和 AnalysisAssistantDock

建议分别抽取：

```text
frontend/src/views/dashboard/common/resource-tree/
├── resourceTreeAdapter.ts
├── resourceTreePersistence.ts
├── resourceTreePermission.ts
├── useResourceTreeOperations.ts
└── ResourceTreeNodeMenu.vue

frontend/src/views/chat/composables/
├── useChatLoader.ts
├── useChatSender.ts
├── useChatStream.ts
├── useChatChartRestore.ts
└── useChatPostAnswerActions.ts

frontend/src/views/analysis-assistant/composables/
├── useAssistantDockInteraction.ts
├── useAssistantConversation.ts
├── useAssistantStream.ts
├── useAssistantExport.ts
└── useAssistantDashboardActions.ts
```

## 5. 后端拆分设计

### 5.1 dashboard_service.py

该文件是最重要的后端拆分对象。建议保持 `dashboard_service.py` 作为兼容门面，避免现有 API、聊天模块、分析助手和测试中的导入立即失效。

建议目录：

```text
backend/apps/dashboard/service/
├── dashboard_access.py
├── dashboard_canvas.py
├── dashboard_tree.py
├── dashboard_query.py
├── dashboard_preview_cache.py
├── dashboard_template.py
├── dashboard_share.py
├── dashboard_crud.py
└── __init__.py
```

建议边界：

- `dashboard_access.py`：当前租户、工作区角色、编辑/查看/分享权限。
- `dashboard_canvas.py`：Canvas JSON 解析、组件 ID 重建、复制和数据源校验。
- `dashboard_tree.py`：树节点、父子关系、排序、默认看板和环检测。
- `dashboard_query.py`：查询准备、Pivot SQL、执行数据源解析、结果规范化。
- `dashboard_preview_cache.py`：Redis/内存缓存、并发锁、信号量、缓存 Key。
- `dashboard_template.py`：平台模板、快照物化、来源看板同步和修复。
- `dashboard_share.py`：分享创建、查看、使用和删除。
- `dashboard_crud.py`：看板资源增删改、复制、默认资源操作。

特别注意：现有 `chat.py` 和 `analysis_assistant.py` 都依赖 `dashboard_service.py`。新拆出的底层模块不能反向依赖聊天 API 或分析助手 API，否则容易形成循环依赖。原文件中被测试 monkeypatch 的符号应继续导出一段时间。

### 5.2 analysis_assistant.py

建议保留 API 路由在原文件，抽取到 `service/`：

```text
backend/apps/analysis_assistant/service/
├── conversation_service.py
├── permission_sanitizer.py
├── report_export.py
├── semantic_context.py
├── analysis_chart_config.py
├── semantic_validation.py
└── analysis_orchestrator.py
```

已有 `analysis_time_policy.py` 和 `analysis_time_sql.py` 应继续作为时间策略的权威实现，不能再在拆分模块中复制一套时间范围选择逻辑。

### 5.3 smart_qa_graph.py 与 llm.py

仓库已有 Smart Q&A LangGraph 设计约束：图只负责编排，提示词、Data Skill、SQL、权限、图表和记录保存行为仍由现有服务承载。因此建议：

- `smart_qa_graph.py` 只保留 State、节点适配器、边和 graph 构建。
- 事件可用性检测、缺失事件 SQL 重写、结果清理抽到 `smart_qa_event_policy.py`。
- 不把节点内部业务逻辑复制到新的“通用 Graph 工具”中。
- `LLMService` 先按内部能力抽取为 context、SQL、chart、persistence、task lifecycle 模块，公共入口和状态字段保持不变。

推荐结构：

```text
backend/apps/chat/task/
├── smart_qa_graph.py
├── smart_qa_event_policy.py
├── llm_context.py
├── llm_sql.py
├── llm_chart.py
├── llm_persistence.py
└── llm_task_runner.py
```

### 5.4 tracking_excel.py 与 tenant.py

`tracking_excel.py` 应拆为：

```text
backend/apps/system/service/tracking_excel/
├── import_reader.py
├── import_parser.py
├── config_merge.py
├── export_rows.py
├── export_writer.py
└── template_builder.py
```

`tenant.py` 应按 API 资源拆为：

```text
backend/apps/system/api/tenant/
├── overview.py
├── members.py
├── applications.py
├── invitations.py
├── bindings.py
└── security.py
```

租户审计写入、成员权限检查和数据源绑定逻辑应继续复用现有服务，不因路由拆分而出现多个版本。

## 6. 可以提炼的公共能力

### 6.1 前端

#### 数据源身份值

当前 `SQPreviewHead.vue`、`SQComponentWrapper.vue`、`AddViewDashboard.vue`、`ChartBlock.vue` 有重复的 ID 转换和比较逻辑。

建议新增 `frontend/src/utils/datasource.ts`：

```ts
normalizeDatasourceId(value: unknown): number | undefined
sameDatasource(left: unknown, right: unknown): boolean
```

数据源加载、激活、权限和当前上下文仍由 `datasourceContext` Store 负责。

#### 图表字段与坐标轴

建议在现有图表工具基础上统一：

```ts
getAxisField(axis): string
normalizeAxisList(value): ChartAxis[]
getAxisLabel(axis): string
getChartBoundFields(chart): string[]
```

优先复用 `frontend/src/views/chat/component/charts/utils.ts` 和 `BaseChart.ts`，不要新增第二套数值格式化、百分比转换和空值判断。

#### 图表配置

现有 `frontend/src/views/dashboard/utils/dashboardChartConfig.ts` 已被聊天和看板共同使用。建议先补齐类型和单测，再决定是否移动到更中性的 `frontend/src/utils/chart/`，不要在移动和逻辑修改中同时改变配置版本。

#### SSE

聊天和分析助手可以共用 SSE 分块解码，但事件到消息状态的 reducer 必须分别保留。公共层只负责协议解码，不负责业务事件解释。

### 6.2 后端

#### 租户上下文

多个 API 自己实现 `_current_tenant_id`。应优先统一使用现有 `apps.system.schemas.access_context.require_current_tenant_id`，并逐个核对允许平台管理员切换租户的特殊语义。

#### SQL 方言

现有 `apps.db.db.normalize_sql_safety_ds_type` 和 `get_sqlglot_dialect` 应作为数据库方言入口。`dashboard_service.py`、`dashboard_date_filter.py`、`analysis_assistant.py` 的重复方言判断应逐步迁移到同一实现。

#### JSON 路径与数据字典表达式

现有 `common/sql_json_paths.py` 和 `apps/system/crud/tracking_expression.py` 已经承担 JSON 路径、标识符和数据源方言表达式能力。新模块应复用它们，不要在 `common/utils/utils.py` 中增加 SQL 字符串拼接。

#### JSON/响应规范化

`common/utils/utils.py` 已经偏向杂项工具。可以将纯序列化、JSON 提取、日志和安全工具逐步分离，但必须保留旧导入门面，避免一次性影响全仓调用方。

## 7. 不建议抽成全局 Utils 的内容

- 业务指标字段猜测、图表类型猜测和漏斗字段推断。
- Data Skill、语义层、跟踪事件和特定数据源的业务口径。
- 租户/数据源/字段/行权限的组合策略。
- 只使用一次、且必须读取页面局部响应式状态的函数。
- 依赖特定组件 DOM、生命周期或 UI 文案的函数。

这些逻辑可以放在领域服务或 composable 中，但不应放入通用工具包。

## 8. 测试与迁移策略

当前前端存在多份直接读取 Vue 源码并使用正则断言的测试，例如 `DashboardSqlEditor.*.test.mjs` 和 `ResourceTree.*.test.mjs`。拆分后如果只移动函数，测试会因为源码位置变化而失效，但不能把测试简单删除。

迁移要求：

1. 先为抽出的纯函数增加模块行为测试。
2. 将源码正则测试改为读取导出的函数、组合式函数或组件契约。
3. 保留少量源码结构测试，只验证关键入口仍存在，不验证内部实现位置。
4. 后端按领域拆分现有测试：Dashboard 权限/执行/模板、Smart Q&A 事件策略/图节点、Excel 导入/导出分别组织。
5. 每个阶段都执行原有聚焦测试，确认权限拒绝、数据源切换、缓存失效、SQL 方言、空结果和流式中断行为不变。

## 9. 实施顺序

### 阶段 0：建立基线

- 保存当前前端构建、类型检查和聚焦测试结果。
- 保存后端 Smart Q&A、Dashboard 权限/执行、分析助手和 tracking Excel 测试结果。
- 记录当前公开 import、API、组件 props/emits 和测试 monkeypatch 点。

### 阶段 1：纯能力抽取

- 前端数据源 ID、图表 axis、配置规范化。
- 后端租户上下文、SQL 方言、JSON 路径复用。
- 为新模块补测试，不修改业务流程。

### 阶段 2：拆 Dashboard 主链路

- 先拆 `dashboard_service.py` 的查询执行、缓存和资源树。
- 再拆 `DashboardSqlEditor.vue` 的预览、Builder、MCP 和保存状态。
- 保留原文件兼容导出，逐个替换调用方。

### 阶段 3：拆助手和聊天链路

- Smart Q&A 事件策略。
- 分析助手会话、报告导出和语义校验。
- LLMService 内部能力模块化。
- Chat 和 Analysis Assistant 的 SSE reducer 测试。

### 阶段 4：管理与导入导出模块

- Tenant API。
- Tracking Excel。
- Datasource API。
- 用户、权限和登录页面按功能拆分。

## 10. 主要风险与控制措施

| 风险 | 控制措施 |
| --- | --- |
| 循环依赖 | 新领域模块不得依赖 API 层；Dashboard 底层模块不得依赖 Chat/Analysis Assistant |
| 权限边界改变 | 保留原权限函数行为，增加租户、数据源和行列权限回归测试 |
| 数据源上下文丢失 | 所有查询、语义、图表和助手流程继续从当前授权数据源上下文读取 |
| 测试因源码移动失效 | 将源码正则测试改为模块行为测试，保留少量入口契约测试 |
| 缓存/并发状态变化 | 不移动模块级可变状态；验证 Redis Key、锁、信号量和请求隔离 |
| Chart DOM 生命周期回归 | 图表实例绑定组件 ref，不使用全局 DOM ID |
| 配置结构被静默改写 | 保留现有 chart config、Pivot、dateFilter 和 MCP 保存格式 |
| 大范围 diff 难以回滚 | 每个领域单独提交，先兼容导出，再迁移调用方 |

## 11. 验收标准

- 原有 API 路径、请求模型、响应结构和前端组件 props/emits 不变。
- `DashboardSqlEditor.vue` 和 `dashboard_service.py` 的主文件只保留编排与兼容导出，不再包含所有领域实现。
- 图表配置、数据源上下文、租户权限和 SQL 方言只有一个权威实现。
- 新抽出的纯函数具备独立测试，关键状态流程具备集成测试。
- 前端完成构建、类型检查、聚焦测试和浏览器路径验证；布局改动额外验证桌面/移动端和横向溢出。
- 后端完成相关 pytest、静态检查、实际 API 调用和监听进程验证。
- 不新增 SLG 专用运行时代码，不新增隐式字段兜底，不删除当前隐藏的 Smart Q&A 分析/预测兼容能力。

## 12. 推荐首个实施切片

建议第一个实际重构切片只做以下内容：

1. 新增前端 `datasource.ts`，统一数据源 ID 规范化。
2. 将 `DashboardSqlEditor.vue` 的预览结果快照和 Preview Merge 抽到 `useSqlPreview.ts`、`useSqlPreviewMerge.ts`。
3. 保持原组件对外接口和保存结构不变。
4. 迁移对应源码正则测试为纯函数测试，并运行 DashboardSqlEditor 聚焦测试。

这个切片的业务风险较低、复用价值明确，可以验证拆分模式后再处理权限、SQL 执行和异步任务等高风险部分。
