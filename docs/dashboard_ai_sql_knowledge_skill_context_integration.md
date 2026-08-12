# AI 看板 Skills 与知识库 RAG 口径联合调用设计

## 1. 文档信息

- 文档类型：后端调用链设计
- 日期：2026-08-12
- 适用接口：`POST /api/v1/dashboard/ai_sql_generate`
- 适用场景：手动 AI 看板配置生成 SQL
- 状态：已实施并完成后端自动化、临时 API 启动与鉴权边界验证

## 2. 目标

在不新增接口、不改变前端调用入口的前提下，让现有 AI 看板 SQL 生成同时使用：

1. 现有 Data Skills 执行规则和统计口径。
2. 事件字典与结构化字段映射。
3. 知识库 RAG 召回的统计分析口径说明和业务背景。

知识库与 Skills 独立治理、运行时联合使用：

- Skills 继续使用 `custom_prompt` 主数据、原管理页面和 `find_data_skills` 选择链路。
- 知识库不包含 Skills，不管理 Skill 生命周期，也不通过 RAG 重新选择 Skill。
- 知识库提供业务知识、统计分析口径、使用条件、限制、注意事项和参考 SQL 示例。

## 3. 修复前问题

`BusinessSemanticContextService` 已能产生以下独立上下文：

```text
tracking_config
skill_text
structured_context
knowledge_context
```

修复前 AI 看板 Prompt 只注入 `data_skill` 和 `tracking_config`。知识库 RAG 已完成召回，响应也能返回 citation 和知识版本 hash，但 `knowledge_context` 没有进入 SQL 生成模型输入。

修复前状态是：

- Skills 调用链已生效。
- 知识库 RAG 召回与引用链已存在。
- RAG 正文尚未参与 AI 看板 SQL 生成。

当前实现已从 `BusinessSqlContext.semantic.knowledge_context` 注入独立知识区块，同时保持 Skills 和事件字典原有通道。

## 4. 设计决策

- 保持现有接口 `POST /dashboard/ai_sql_generate`。
- 保持前端 `dashboardApi.generate_ai_sql(...)` 调用。
- 保持 `find_data_skills`、显式 `data_skill_id` 和自动 Skill 匹配逻辑。
- 保持 `<data-skill>` 与 `<tracking-config>` Prompt 区块。
- 给现有内部 Prompt 函数新增必传 `knowledge_context` 参数。
- 新增独立 `<knowledge-context>` 区块，不把知识正文拼入 `<data-skill>`。
- 内部函数调用方必须一次性更新，不保留缺少 `knowledge_context` 的旧签名兼容或静默回退。

## 5. 完整调用链

```text
DashboardSqlEditor.vue
  -> POST /dashboard/ai_sql_generate
  -> collect_context
  -> normalize_manual_config
  -> build_business_sql_context
     -> PermissionScopeService.build_snapshot
     -> find_data_skills
     -> 授权 Schema / allowed_tables
     -> tracking context
     -> structured knowledge context
     -> KnowledgeRetrievalService.search
  -> data_skill + tracking_config + knowledge_context
  -> build_formula_ir
  -> deterministic_validate
  -> build_sql_plan
  -> LLM generate_sql
  -> validate_sql
  -> finalize_response
```

接口权限、确定性配置校验和 SQL 后置校验保持现状。

## 6. Skills 调用约束

Skills 继续使用当前权威链路：

```text
data_skill_id 显式选择或自动匹配
  -> eligible_data_skill_ids 权限与对象适用性过滤
  -> find_data_skills
  -> foundation Skill
  -> 覆盖去重和数量限制
  -> BusinessSqlContext.data_skill
  -> <data-skill>
```

本次不能：

- 把 Skill 建成知识库条目。
- 通过知识库 RAG 选择或替换 Skill。
- 把知识正文拼进 `data_skill` 后当成 Skill 执行规则。
- 在显式 Skill 无权或不适用时自动换成知识库口径。

## 7. 知识库 RAG 召回

### 7.1 召回入口

知识库内容必须通过现有 `KnowledgeRetrievalService.search(...)` 召回。Dashboard 模块不得直接查询知识库表、全量读取正文或按名称猜测知识条目。

召回由：

```text
BusinessSqlContextService.build(
    surface="dashboard_ai_sql",
    question=<规范化后的看板检索问题>,
)
```

进入 `BusinessSemanticContextService.build(...)` 后执行。

### 7.2 检索问题构造

RAG 查询应包含：

- 规范化后的看板意图、标题和图表类型。
- 时间字段、指标、公式指标、分组和筛选配置。
- `surface=dashboard_ai_sql`。
- 当前用户授权后的 Schema 摘要。
- 当前允许访问的数据表范围。
- 已由 `find_data_skills` 选中的 Skill 摘要。

已选 Skill 摘要只用于提升知识召回相关性，不改变 Skill 选择结果或优先级。

### 7.3 权限与适用性边界

召回必须受以下条件共同约束：

- 当前 `tenant_id` 和工作空间绑定的数据源。
- 当前用户数据源访问权限。
- `PermissionScopeSnapshot` 中的 Schema、表、字段、事件和 JSON Path 范围。
- 知识作用域和当前已发布版本。
- 平台知识对当前工作空间/数据源的适用性。
- 当前工作空间对平台知识的停用状态。
- AI 场景 `dashboard_ai_sql`。

不得召回：

- 其他工作空间知识。
- 未发布或已失效版本。
- 当前工作空间已停用的平台知识。
- 当前数据源不适用或引用无权对象的知识。

### 7.4 召回结果

同一次 RAG 召回固定产生：

```text
knowledge_context
knowledge_citations
knowledge_version_hash
retrieval_warnings
retrieval_failure_type
```

`knowledge_context` 进入 LLM Prompt。citation、版本 hash、warning 和 failure type 进入接口响应与上下文快照，用于审计和问题复现。

同一次 SQL 生成请求不得在生成、修复或最终响应阶段重新召回不同版本的知识。

### 7.5 正文格式

召回正文保持低优先级标记：

```xml
<retrieved-knowledge priority="reference-only" id="chunk-id">
统计分析口径说明
</retrieved-knowledge>
```

外层 Prompt 使用独立区块：

```xml
<knowledge-context>
  ...RAG 召回正文...
</knowledge-context>
```

## 8. LLM Prompt 契约

修改后的用户 Prompt 保持三个独立区块：

```xml
<data-skill>
  ...当前请求选中的 Skills...
</data-skill>

<tracking-config>
  ...事件字典和字段映射...
</tracking-config>

<knowledge-context>
  ...RAG 召回的统计分析口径说明...
</knowledge-context>
```

建议的内部函数契约：

```python
def _dashboard_config_prompt(
    request: DashboardAiSqlGenerateRequest,
    datasource: CoreDatasource,
    data_skill: str,
    tracking_config: str,
    knowledge_context: str,
    *,
    schema: str = "",
    sql_dialect: str | None = None,
    allowed_tables: list[str] | None = None,
) -> str:
    ...
```

`knowledge_context` 为必传参数。调用方必须显式传空字符串表示本次没有知识上下文，不能通过默认参数保留旧内部调用签名。

知识正文长度由 `KnowledgeRetrievalService` 按 `KNOWLEDGE_RETRIEVAL_MAX_CONTEXT_CHARS` 在同一次召回中统一约束。Dashboard Prompt 不得再次截断正文；检索服务对首个超长切片截断 citation 正文本身，并始终输出完整的 `<retrieved-knowledge>` 标签，保证 Prompt 正文与 citation 快照一致。

## 9. 信息权威顺序

发生冲突时必须遵循：

```text
权限与当前工作空间/数据源上下文
  > 用户在看板中明确选择的字段、指标、筛选、公式和时间配置
  > 授权后的物理 Schema
  > 已发布的结构化事件、字段和 JSON 映射
  > 当前请求选中且通过权限裁剪的 Data Skills
  > 知识库 RAG 召回的统计分析口径和业务说明
  > 模型自身常识
```

知识库中的命令、权限声明、SQL 示例或指标说明不能：

- 覆盖已选 Data Skills。
- 扩大表、字段、事件或行权限。
- 替换当前工作空间绑定的数据源。
- 修改结构化字段或 JSON Path 映射。
- 绕过只读 SQL、日期参数或确定性校验规则。

## 10. 失败与降级

| 状态 | 处理方式 |
| --- | --- |
| RAG 成功且有结果 | 注入 `<knowledge-context>`，返回 citations 和版本 hash |
| RAG 成功但无匹配 | `knowledge_context` 为空，Skills 与事件字典继续生效 |
| 无符合权限/适用性的知识 | 不扩大范围，记录 failure type |
| 可降级检索失败 | 不伪造知识，保留 warning/failure type，Skills 继续生效 |
| 权限或数据源失败 | 明确拒绝请求，不得当作“没有知识”继续生成 |

禁止按相似名称、其他数据源、其他工作空间或全局知识静默替代。

## 11. 响应和审计

现有响应字段继续保留：

```text
knowledge_citations
knowledge_version_hash
retrieval_warnings
retrieval_failure_type
context_snapshot
```

响应 citation 只允许包含知识库 ID/名称、版本、切片、章节、来源文件、相关分数和可见范围等安全元数据，不返回知识正文。

上下文快照需同时保留：

- 选中的 Skill ID、选择模式和内容 hash。
- 权限版本和 Schema hash。
- 知识版本 hash 和 citation 摘要。
- 检索 warning 与 failure type。

## 12. 运行开关

知识库 RAG 生效需要：

```text
KNOWLEDGE_RUNTIME_CONTEXT_ENABLED=true
KNOWLEDGE_RETRIEVAL_ENABLED=true
```

开关关闭时：

- Skills 与事件字典继续按原链路进入 Prompt。
- `knowledge_context` 为空。
- 不使用其他内容模拟知识库召回。

本次不修改两个开关的默认值和灰度发布策略。

## 13. 测试要求

至少覆盖：

1. `find_data_skills` 和显式 `data_skill_id` 行为不变。
2. `<data-skill>` 中仍包含选中的 Skill 正文。
3. RAG 正文进入独立 `<knowledge-context>`。
4. 知识正文没有被拼入 `<data-skill>`。
5. 检索查询包含规范化看板配置、授权 Schema/表和已选 Skill 摘要。
6. 无结果时知识区块为空，Skills 继续生效。
7. 无权限或不适用知识不会被召回。
8. warning/failure type 能进入响应和快照。
9. citation 不泄露知识正文。
10. Prompt 明确知识库不能覆盖 Skills、权限、Schema 和 SQL 安全规则。
11. 现有表字段权限、只读、多语句、日期参数、公式和 JSON 映射测试继续通过。

## 14. 实施文件

主要修改：

- `backend/apps/dashboard/crud/ai_sql_generator.py`
- `backend/apps/knowledge_base/retrieval.py`
- `backend/tests/test_knowledge_dashboard_ai_sql.py`
- `backend/tests/test_dashboard_ai_sql_generator.py`
- `backend/tests/test_knowledge_base_retrieval.py`
- `.trellis/spec/backend/knowledge-base-rag.md`

复用但原则上不修改：

- `backend/apps/datasource/crud/sql_engine.py`
- `backend/apps/datasource/crud/semantic_context.py`
- `backend/apps/chat/curd/custom_prompt.py`

## 15. 回滚

运行时紧急降级可关闭：

```text
KNOWLEDGE_RUNTIME_CONTEXT_ENABLED=false
KNOWLEDGE_RETRIEVAL_ENABLED=false
```

关闭后只停止知识库召回和注入，不影响 Skills 选择与 LLM 调用。代码回滚则恢复该次提交前的 Prompt 函数签名和 graph state。

## 16. 实施验证

已完成：

- 针对 Dashboard Prompt、统一语义上下文和知识检索的后端回归测试：`74 passed`。
- Ruff 检查通过。
- 受影响 Python 文件 `py_compile` 通过。
- `git diff --check` 通过。
- 使用当前工作区代码在 `127.0.0.1:8010` 启动临时 API，应用启动完成后已停止，端口已释放。
- `GET /api/v1/system/getLoginMethod` 和未带 Token 的 `POST /api/v1/dashboard/ai_sql_generate` 均返回 `401`，验证服务可用且鉴权边界生效。
- 启动前核对 `LLM_REQUEST_TIMEOUT=120`、`LLM_TASK_MAX_WAIT_SECONDS=900`、`LLM_MAX_RETRIES=1`。

环境限制：

- 当前仓库缺少独立 `backend/.venv`，测试复用 `D:\AIWork3\chat-bi\backend\.venv`。
- 该虚拟环境的 mypy 安装缺少 `0aca9ce3d91742c5b361__mypyc`，类型检查无法启动；这不是代码类型错误结论。
- 当前没有可复用的认证 Token，因此未执行认证后的真实知识召回与 LLM SQL 生成请求。上线或联调时仍需按第 12 节开启两个知识开关，并用有权限账号验证 SQL、citation 和上下文快照来自同一次召回。
