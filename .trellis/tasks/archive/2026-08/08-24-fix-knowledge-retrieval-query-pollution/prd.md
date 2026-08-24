# 修复知识库检索查询污染

## Goal

让知识库向量召回始终表达当前请求的主分析意图，避免授权 Schema、表名和自动选择的 Data Skill 正文淹没用户问题，导致 Smart Q&A、AI 看板、分析助手或报告解读引用与问题无关的知识块。

## Background

- 2026-08-24 的真实 Smart Q&A 请求“商店购买”在 `datasource_id=3` 下引用了 MAU、WAU、DAU、新增用户和付费用户。
- 只对“商店购买”生成向量时，上述五个知识块的余弦相似度为 `0.220-0.285`，均低于当前最低阈值 `0.40`。
- 当前统一语义层在 [backend/apps/datasource/crud/semantic_context.py](../../../backend/apps/datasource/crud/semantic_context.py) 中把问题、场景、允许访问的表、最多 4000 字 Schema 和最多 12 个 Data Skill 摘要拼成一个检索字符串。真实请求因此把五个无关知识块的分数抬高到 `0.652-0.704`。
- 同一请求自动选中了 12 个 Data Skill，Skill 总正文约 23511 字，并反复包含 DAU、活跃、付费、人数和去重主体等通用指标词。
- 既有权限快照、数据源适用性、对象引用解析和发布生命周期过滤负责候选边界；这些边界不要求把 Schema 或 Skill 正文写入相似度查询。
- 历史 AI 看板设计曾明确要求把 Schema、表和 Skill 摘要加入 RAG 查询，以提升召回相关性；本次真实故障证明该决策会产生查询污染，需要修正当前运行契约和对应文档。

## Requirements

- R1：`KnowledgeRetrievalService.search(...)` 的 `query` 只能来自调用方已经构造好的主意图文本，并进行空白清理；不得再追加 `surface`、Schema、允许表或 Data Skill 摘要。
- R2：Smart Q&A 使用用户问题；AI 看板继续使用 `_dashboard_normalized_retrieval_query(...)` 产生的规范化看板意图；报告解读和分析助手继续使用各自已有的有界任务查询。统一语义层不得二次扩写这些查询。
- R3：Schema、允许表、Data Skill、tracking 配置和结构化知识继续按现有职责参与权限过滤、Skill 选择、SQL/分析 Prompt 和上下文快照；本次只将它们从知识相关性向量输入中移除。
- R4：保持当前租户、数据源、用户权限、发布版本、归档状态、工作空间停用、适用性、语义对象引用和 embedding 签名过滤不变。
- R5：保持当前 `KNOWLEDGE_RETRIEVAL_MIN_SCORE`、Top-K、上下文长度、citation、知识版本 hash、warning、failure type 和审计结构不变；不得通过提高全局阈值或硬编码“商店购买”等特例修复。
- R6：空主意图必须继续进入现有 `EMPTY_QUERY` 路径，不得因存在场景、Schema 或 Skill 而产生知识召回。
- R7：更新仍描述“Schema/表/Skill 摘要参与检索查询”的现行文档和后端 RAG 规范，明确辅助上下文只能约束候选与下游执行，不能污染相关性查询。历史归档任务只保留为决策记录，不回写。
- R8：回归测试必须覆盖统一语义层的真实调用边界，证明问题文本在 Schema、表和 Skill 内容变化时保持不变，并覆盖空问题。

## Acceptance Criteria

- [ ] AC1：统一语义层收到问题“商店购买”以及包含 MAU/WAU/DAU/付费等词的 Schema、表和 Skill 时，传给检索服务的 `query` 仍严格等于“商店购买”。
- [ ] AC2：同一问题在 Schema、允许表和自动选择 Skill 变化后，知识检索 `query` 及其 `query_hash` 不变。
- [ ] AC3：空白问题不会被场景、Schema、表或 Skill 补成非空查询，并由检索服务返回现有 `EMPTY_QUERY` 结果。
- [ ] AC4：Smart Q&A、AI 看板、分析助手和报告解读继续通过统一语义服务获得知识上下文，且各入口已有的主意图构造函数保持生效。
- [ ] AC5：权限、数据源适用性、发布生命周期、embedding 签名、阈值、Top-K、citation 和审计相关回归测试通过。
- [ ] AC6：真实本地 Smart Q&A 请求“商店购买”后，最新检索审计的 `query_hash` 等于清理后主意图的 SHA-256，且不再引用 MAU、WAU、DAU、新增用户或付费用户等由辅助上下文造成的无关结果；若没有合格知识则允许返回 0 条。
- [ ] AC7：后端定向测试通过，完整本地栈重启后 API、MCP、Worker、前端均正常，实际页面路径完成验证。

## Out Of Scope

- 新增 cross-encoder、LLM reranker、BM25 或混合检索引擎。
- 修改 Data Skill 自动选择算法或最多 12 个 Skill 的限制；Skill 误选的独立问题不再影响知识召回，但可另行治理。
- 调整知识切片大小、重叠长度、embedding 模型、最低分数或 Top-K。
- 增加用户手动选择知识库的前端入口。
- 修改知识库内容、Data Skill 数据或业务指标口径。

## Notes

- 本任务是统一后端检索契约修复，不是只针对截图组件或单一 Smart Q&A 调用点的局部补丁。
