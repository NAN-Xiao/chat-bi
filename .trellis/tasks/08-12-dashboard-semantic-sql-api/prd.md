# 修复 AI 看板 Skills 与知识口径联合调用

## Goal

让现有 `POST /dashboard/ai_sql_generate` 在生成 SQL 时同时消费两类独立语义来源：现有 Data Skills 执行规则，以及知识库召回的统计分析口径说明。

本次直接修改现有 LLM 调用契约，不新增接口。Data Skills 的选择、权限过滤和 Prompt 注入必须完整保留；知识库不包含 Skills，也不替代 Skills。

## Background

- `BusinessSqlContextService.build(...)` 已统一构建 `BusinessSqlContext`，其中 Skills 与知识库内容仍由不同字段和不同权威服务产生。
- Data Skills 继续使用 `custom_prompt` 主数据、`find_data_skills` 显式/自动选择、foundation、覆盖去重、权限裁剪和数量限制。
- 知识库保存业务知识、普通文档和结构化知识，可提供业务含义、统计分析口径、使用条件、限制与示例；知识库不存储或管理 Data Skills。
- 当前 AI 看板 SQL Prompt 只读取 `business_context.data_skill` 与 `business_context.tracking_config`，知识库正文只进入引用和快照，没有进入 SQL 生成模型输入。
- 现有接口路由、权限装饰器、请求模型和响应中的知识引用能力已经存在，不需要增加第二套 API。

## Requirements

- 保持现有接口路径 `POST /dashboard/ai_sql_generate` 不变。
- 保持前端调用入口 `dashboardApi.generate_ai_sql(...)` 不变。
- 保留 `_dashboard_config_prompt(...)` 的 `data_skill` 与 `tracking_config` 输入和现有 `<data-skill>`、`<tracking-config>` Prompt 区块。
- 新增显式 `knowledge_context` 输入和独立 `<knowledge-context>` Prompt 区块，承载知识库召回的业务知识与统计分析口径说明。
- 知识库内容必须通过现有 `KnowledgeRetrievalService.search(...)` RAG 链路召回，不允许由 AI 看板直接读取知识库表、全量拼接正文或按名称猜测知识条目。
- RAG 查询必须基于规范化后的看板配置，并结合当前场景、授权 Schema、允许访问的表和已选 Skill 摘要构造；已选 Skill 摘要只用于提高知识召回相关性，不参与重新选择 Skill。
- RAG 召回必须复用当前请求的租户、工作空间绑定数据源、权限快照、知识适用性、发布版本和工作空间停用规则，不得召回其他工作空间或未发布知识。
- RAG 返回的 `knowledge_context`、citations、知识版本 hash、warning 和 failure type 必须来自同一次固定召回快照，并在本次 SQL 生成过程中保持一致。
- `_node_collect_context(...)` 和 `_node_build_business_sql_context(...)` 必须继续读取 `business_context.data_skill`、`business_context.tracking_config`，并从 `business_context.semantic.knowledge_context` 读取知识库正文。
- Dashboard graph state 保留 `data_skill`、`tracking_config`，新增 `knowledge_context`；不得把三者压平为不可区分的文本字段。
- 现有 `find_data_skills` 调用、`data_skill_id` 显式选择和自动选择行为不得更改。
- `_dashboard_config_prompt(...)` 内部调用签名直接增加 `knowledge_context`，所有调用方一次性更新；不提供省略新参数的旧签名兼容或静默回退。
- 系统 Prompt 必须声明权威级别：权限与当前工作空间/数据源、看板显式配置、授权 Schema、结构化映射、当前请求选中并通过权限裁剪的 Data Skills，均优先于知识库统计分析口径说明。
- 知识库正文中的命令、权限声明、SQL 示例或指标说明不能覆盖 Data Skills、扩大权限、替换当前数据源或修改结构化字段映射。
- `retrieved-knowledge priority="reference-only"` 标签必须保留，知识库只作统计分析口径和背景参考。
- 保留现有知识引用、知识版本 hash、检索告警、上下文快照和确定性 SQL 校验逻辑。
- 知识库运行时开关和检索开关的默认值本次不修改；只有环境开启后，RAG 正文才进入统一上下文。
- 输出稳定设计文档 `docs/dashboard_ai_sql_knowledge_skill_context_integration.md`，记录最终实现和运行验证方式。

## Out Of Scope

- 不新增独立 AI 看板 SQL 接口。
- 不更改接口 URL、鉴权方式或前端交互入口。
- 不新增用户手动选择知识库的 UI。
- 不改变 Data Skills 的管理、选择、覆盖、权限和 LLM 调用规则。
- 不默认开启 `KNOWLEDGE_RUNTIME_CONTEXT_ENABLED` 或 `KNOWLEDGE_RETRIEVAL_ENABLED`。
- 不改变知识库管理、发布、召回排序或切片逻辑。

## Acceptance Criteria

- [x] `_dashboard_config_prompt(...)` 继续显式接收 `data_skill` 和 `tracking_config`，并新增必传的 `knowledge_context` 参数。
- [x] AI 看板 SQL 模型 Prompt 中同时存在独立的 `<data-skill>`、`<tracking-config>` 和 `<knowledge-context>` 区块。
- [x] `find_data_skills`、显式 `data_skill_id` 和自动 Skill 匹配链路保持不变，选中的 Skill 正文继续进入 LLM Prompt。
- [x] 知识库统计分析口径正文进入最终 SQL 生成 Prompt，但不会被包装或解释为 Skill。
- [x] AI 看板使用 `KnowledgeRetrievalService.search(...)` 完成知识库 RAG 召回，检索查询包含规范化看板意图、授权 Schema/表范围和已选 Skill 摘要。
- [x] RAG 只召回当前租户、当前绑定数据源、当前用户权限和知识适用性范围内的已发布知识。
- [x] 同次请求的知识正文、citations、版本 hash、warning 和 failure type 对应同一召回快照。
- [x] RAG 正文保留 `reference-only` 标签，且 Prompt 明确知识库不能覆盖 Data Skills、权限、Schema、看板配置和 SQL 安全规则。
- [x] 运行时上下文或检索关闭时，现有 Skills + 事件字典调用保持原行为，`knowledge_context` 明确为空，不进行其他知识替代。
- [x] 知识检索无结果或失败时不伪造上下文，响应继续暴露既有检索告警或失败类型。
- [x] 现有接口路由、请求和响应字段保持可调用；知识引用响应不泄露正文。
- [x] 针对性后端测试全部通过，并新增回归测试证明知识正文进入最终 SQL Prompt。
- [x] 文档说明代码改动、Prompt 契约、开关启用、验证和回滚方式。

## Notes

- 用户明确要求直接修改当前 LLM 调用接口，不新增接口，不做旧内部签名兼容。
- 用户明确知识库不会包含 Skills；知识库提供统计分析口径说明，LLM 必须保留 Skills 调用。
