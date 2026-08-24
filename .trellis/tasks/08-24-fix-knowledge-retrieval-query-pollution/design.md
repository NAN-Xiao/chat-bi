# Technical Design

## Problem Boundary

当前统一语义链路为：

```text
surface-specific primary intent
  -> Data Skill selection
  -> authorized Schema / allowed tables
  -> _retrieval_query(question, surface, schema, allowed_tables, skill_list)
  -> one embedding for the combined text
  -> permission-first candidate filtering
  -> similarity threshold + Top-K
```

错误发生在“相关性输入”边界：权限和执行上下文被当成查询语义拼入同一个向量。短问题会被长 Schema 和 Skill 摘要支配，即使候选过滤完全正确，也会在合格候选中排出错误的知识块。

## New Contract

统一语义层只规范化调用方主意图：

```python
def _retrieval_query(question: str | None) -> str:
    return str(question or "").strip()
```

调用保持通过同一个 `KnowledgeRetrievalService.search(...)`：

```text
primary intent only
  -> query embedding
  -> existing permission / datasource / applicability filters
  -> existing min score + Top-K
  -> existing context / citations / audit
```

`surface` 继续作为审计字段传递，不进入向量。`schema`、`allowed_tables` 和 `skill_list` 继续在 `BusinessSemanticContextService.build(...)` 中产生并用于各自既有职责，但不再传给 `_retrieval_query`。

## Surface Behavior

| Surface | Primary retrieval intent after fix |
| --- | --- |
| Smart Q&A | 用户问题文本 |
| AI dashboard SQL | `_dashboard_normalized_retrieval_query(...)` 输出的看板意图、指标、分组和筛选 |
| Report interpretation | `_report_retrieval_query(...)` 输出的报告任务摘要 |
| Analysis assistant | 调用方传入统一语义服务的当前分析问题 |
| Knowledge management preview | 现有直接输入文本；不经过统一语义扩写，行为不变 |

调用方已经负责把其结构化任务压缩为可检索的主意图。统一语义层不得再次附加另一套上下文。

## Authority And Security

- 权限快照和数据源绑定仍在检索前固定。
- 候选仍按当前发布版本、未归档、工作空间 override、知识可见范围、数据源适用性和对象权限过滤。
- Schema 不进入向量不代表取消 Schema 权限；它仍通过 `PermissionScopeSnapshot.schema_hash`、适用性和对象解析约束候选。
- Data Skill 仍是下游 SQL/分析执行的高优先级规则，只是不再改变知识块与问题的相关性分数。
- 无匹配知识明确返回空结果，不使用辅助上下文制造召回。

## Compatibility

- HTTP API、请求响应和 citation 结构不变。
- `KnowledgeRetrievalService.search(...)` 签名不变。
- `_retrieval_query` 是模块内部函数，直接收窄签名，不保留接受旧辅助参数的兼容重载。
- 现有检索审计继续只保存 query hash，不保存问题正文。修复后同一主意图跨 Schema/Skill 变化应产生稳定 hash。

## Testing Strategy

1. 用捕获型 retrieval fake 断言统一语义服务传入的准确 `query`。
2. 用两组不同 Schema、允许表和 Skill 内容构建同一问题，断言查询相同。
3. 用空白问题断言没有辅助内容补全，并覆盖 `EMPTY_QUERY`。
4. 运行知识检索、统一语义、Dashboard、分析助手相关定向测试，确认跨入口契约不回退。
5. 重启完整本地栈，通过真实 Smart Q&A 提问“商店购买”，核对页面引用和 `knowledge_retrieval_log`。

## Documentation And Spec

- 更新 `docs/dashboard_ai_sql_knowledge_skill_context_integration.md`，移除 Schema/表/Skill 参与 RAG 相似度输入的现行说明。
- 更新 `.trellis/spec/backend/knowledge-base-rag.md`，记录“主意图优先、辅助上下文不进入相关性向量”的可执行契约和回归场景。
- 不修改归档任务；其内容作为旧决策和本次修正原因保留。

## Rollback

代码回滚可恢复旧查询构造。紧急运行时降级仍使用独立的 `KNOWLEDGE_RETRIEVAL_ENABLED=false`，不影响 Data Skill 和结构化上下文。由于本次没有数据库或数据迁移，不需要数据回滚。
