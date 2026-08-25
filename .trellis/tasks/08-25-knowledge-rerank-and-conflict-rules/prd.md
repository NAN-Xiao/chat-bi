# 知识库向量召回增加重排与冲突规则

## Requirements

- 对知识库候选分块执行向量初召回。
- 对初召回候选调用可配置的 Rerank 模型进行二次打分。
- 最终结果按 Rerank 分数降序排列，只将达到最低相关性阈值的分块发送给 LLM。
- 召回结果需要向 LLM 标识最终排名和相关性分数。
- AI Prompt 必须要求：仅使用与当前问题相关的知识片段，忽略无关片段。
- AI Prompt 必须要求：知识库内容互相矛盾时，直接说明存在冲突，不自行选择结论。
- Rerank 服务失败时不得静默使用未经重排的知识正文。
- 知识文档上传后只按 Markdown 格式切分并校验知识块结构，不校验数据源、权限、Schema、表字段、JSON Path、事件或 SQL 对象声明。

## Acceptance Criteria

- 向量候选与最终 Rerank 结果的排序、过滤行为有单元测试覆盖。
- Rerank HTTP 请求使用独立的配置模型、API 地址、密钥和超时设置，并兼容 OpenAI-compatible `/rerank` 响应。
- 既有权限过滤、Top-K、上下文长度限制和引用展示契约保持有效。
- Smart Q&A 和手动看板 SQL Prompt 均包含两条知识库处理规则。
- 后端相关测试、ruff 和 mypy 通过，且 `git diff --check` 通过。
