# Implementation Plan

## Code Changes

- [x] 更新 `DashboardManualChartGraphState`，保留 `data_skill`、`tracking_config` 并新增 `knowledge_context`。
- [x] 修改 `_dashboard_config_prompt(...)` 签名，保留 Skills/事件字典输入并新增必传 `knowledge_context`。
- [x] 保留 `<data-skill>`、`<tracking-config>`，新增独立 `<knowledge-context>` Prompt 区块。
- [x] 修改 `_dashboard_sql_user_prompt(...)`，分别传 graph state 的 Skills、事件字典和知识上下文。
- [x] 修改 `_node_collect_context(...)` 的初始问题 Prompt 调用。
- [x] 修改 `_node_collect_context(...)` 与 `_node_build_business_sql_context(...)`，保留 `business_context.data_skill`、`tracking_config`，并写入 `business_context.semantic.knowledge_context`。
- [x] 确认 AI 看板继续以规范化配置调用 `BusinessSqlContextService.build(surface="dashboard_ai_sql")`，由现有 `KnowledgeRetrievalService.search(...)` 执行 RAG，不在 Dashboard 模块新增知识表直读逻辑。
- [x] 在系统 Prompt 增加权限、Schema、显式配置、安全规则、Skills 和 `reference-only` 知识的权威级别约束。
- [x] 更新所有受影响单元测试调用，不保留旧签名测试适配器。
- [x] 新增 Skills 仍进入 Prompt、知识库正文独立进入 Prompt、知识不覆盖 Skills、知识关闭时为空的回归测试。
- [x] 新增 RAG 查询使用规范化看板配置、授权表范围和已选 Skill 摘要的回归测试。
- [x] 新增无匹配知识、无适用知识、检索告警/失败类型以及 citation 不泄露正文的回归测试。
- [x] 新增或更新 `docs/dashboard_ai_sql_knowledge_skill_context_integration.md`。

## Validation

从 `backend/` 运行：

```powershell
D:\AIWork3\chat-bi\backend\.venv\Scripts\python.exe -m pytest tests/test_knowledge_dashboard_ai_sql.py tests/test_dashboard_ai_sql_generator.py tests/test_business_semantic_context.py tests/test_knowledge_base_retrieval.py -q
```

静态检查：

```powershell
rg -n "<data-skill>|<tracking-config>|<knowledge-context>|knowledge_context" backend/apps/dashboard backend/tests
```

运行验证前按本仓库标准启动完整栈，并显式启用知识运行时与检索；核对：

```text
LLM_REQUEST_TIMEOUT=120
LLM_TASK_MAX_WAIT_SECONDS=900
LLM_MAX_RETRIES=1
```

对现有 `POST /api/v1/dashboard/ai_sql_generate` 发起认证请求，验证响应包含 SQL、citation 和上下文快照，并从调试输出确认检索知识进入模型 Prompt。

## Risk Points

- `_dashboard_config_prompt(...)` 在测试中调用较多，新增必传参数后必须一次性更新全部调用方，不留旧签名默认值。
- 统一上下文长度增加可能影响模型延迟；长度只由检索服务按最终完整标签统一约束，Dashboard Prompt 不二次截断。
- `reference-only` 安全约束必须出现在系统 Prompt，不能只依赖知识正文标签。
- 不得将知识库口径拼入 `data_skill`，否则会破坏 Skills 的独立选择、审计和权威语义。
- 不得修改默认知识库开关，避免绕过现有灰度发布策略。

## Documentation

正式文档记录现状、改后链路、内部函数契约、Prompt 权威顺序、开关、测试、上线和回滚方式。

## Review Results

- 修复检索服务首个超长切片绕过最终 Prompt 长度上限的问题；现在按完整 `<retrieved-knowledge>` 序列化长度裁剪 citation 正文并保留闭合标签。
- 修复 Dashboard 上下文快照把 `semantic_context` 合并正文误记为 Data Skill 的问题；现在只对 `business_context.data_skill` 计算 Skill hash 和长度。
- `Ruff`、`py_compile`、74 个针对性 `pytest` 和 `git diff --check` 通过。
- `python -m mypy` 与 `mypy.exe` 均因当前复用虚拟环境缺失 `0aca9ce3d91742c5b361__mypyc` 失败，属于环境阻塞，未发现可用的替代 mypy 入口。
- 使用当前工作区代码和已知 `.env` 配置在 `127.0.0.1:8010` 启动临时 API，确认应用启动完成；验证结束后已停止进程并释放端口。
- 启动前核对 `LLM_REQUEST_TIMEOUT=120`、`LLM_TASK_MAX_WAIT_SECONDS=900`、`LLM_MAX_RETRIES=1`。
- 未认证的登录方法和 AI 看板 SQL 接口请求均返回 `401`，鉴权边界生效。
- 当前没有可复用认证 Token，未执行认证后的真实 RAG + LLM SQL 生成请求；该项保留为联调验证，不影响本次代码与自动化验收结论。
