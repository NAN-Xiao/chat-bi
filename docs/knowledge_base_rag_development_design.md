# 知识库、Skills 与 RAG 统一调用链开发设计

## 1. 文档信息

- 文档类型：开发设计文档
- 日期：2026-08-03
- 状态：待评审
- 需求基线：`docs/knowledge_base_rag_requirements.md`
- 适用范围：知识库管理、Skills 选择链路复用、结构化知识、版本发布、RAG 检索、Smart Q&A、AI 看板、看板报告解读和综合分析助手

本文已纳入需求讨论后的最新确认项；与需求基线中“Data Skills 作为知识类型”等早期表述冲突时，以本文的“知识库与 Skills 独立治理、运行时融合”方案为开发基线，后续需同步修订需求文档。

本文描述如何在当前代码基础上实现需求，不改变以下已确认产品决策：

- 知识库是知识内容的统一管理入口；Skills 保留独立管理入口和生命周期。
- 确定性知识保留结构化运行能力，不退化为纯文档 RAG。
- 知识库支持普通文档、业务知识、事件参数对照和 JSON 字段解析四类知识。
- 四类知识都区分平台公共知识和工作空间知识。
- Skills 保留平台公共、工作空间和个人空间三级作用域，不作为知识库知识类型。
- Skills 按当前项目逻辑选择：用户传入 `data_skill_id` 时优先使用指定 Skill，未传入时由现有 `find_data_skills` 自动匹配。
- 保存草稿、校验后手动发布，第一期只支持单条发布。
- 所有已发布知识默认用于全部 AI 场景。
- 工作空间不能覆盖平台知识，但可以在本工作空间停用平台知识。
- 平台公共知识中的物理对象在使用时动态校验当前工作空间绑定的数据源。
- 事件、Schema、表、字段、JSON Path 和行级数据权限同时参与召回前与生成后校验。
- 第一阶段不修改现有 Skills 页面、API、存储和选择语义，只在现有选择结果进入统一上下文时增加权限交集、知识融合、引用和审计。
- 本设计不包含 MCP 的管理、绑定或调用链改造。

## 2. 当前代码基线

### 2.1 已有知识库

现有代码：

- `backend/apps/knowledge_base/models.py`
- `backend/apps/knowledge_base/api/knowledge_base.py`
- `backend/apps/knowledge_base/tasks.py`
- `backend/alembic/versions/122_create_knowledge_base.py`
- `frontend/src/views/knowledge-base/index.vue`
- `frontend/src/api/knowledgeBase.ts`

已有能力：

- `knowledge_base` 单表保存文档元数据、正文、文件和处理状态。
- 支持 `PLATFORM_PUBLIC` 和 `ADMIN_PUBLIC`。
- 支持 Markdown、Word 上传，最大 50 MB。
- 使用 Redis Worker 解析文档；入队异常时会退化到 FastAPI BackgroundTask。
- 页面支持列表、搜索、上传、编辑元数据、删除和原文详情。

主要缺口：

- 无知识类型、稳定标识、结构化 payload。
- 无草稿版本、发布版本、历史版本和回滚。
- 无切片、向量、检索、引用和检索审计。
- 更新文件会直接替换旧文件，无法保证新版本失败时旧版本继续可用。
- 无工作空间级平台知识停用。
- 未进入任何 AI 运行上下文。

### 2.2 已有 Data Skills

现有代码：

- `backend/apps/chat/models/custom_prompt_model.py`
- `backend/apps/chat/curd/custom_prompt.py`
- `backend/apps/chat/curd/custom_prompt_embedding.py`
- `backend/apps/system/api/custom_prompt.py`
- `frontend/src/views/data-skills/index.vue`

已有能力：

- `custom_prompt.type=DATA_SKILL` 保存 Skill。
- 已有平台、工作空间和用户私有作用域。
- 已有场景范围、数据源范围、向量匹配、用户启停和 SQL 规则校验。
- Embedding 以 Text/JSON 保存，应用层计算余弦相似度。

主要缺口：

- 保存后直接生效，无独立发布版本。
- 无统一的 Skill 选择审计、运行快照和跨场景调用记录。
- 既有权限过滤需要补齐事件、Schema、表、字段、JSON Path 与用户边界的交集校验。
- 当前平台 Skill 的数据源范围偏向固定 datasource ID，不能直接满足“对使用方工作空间数据源动态校验”的新规则。

兼容约束：

- 现有 Skills 页面、API、`custom_prompt` 存储、启停和既有调用逻辑在第一阶段保持权威且不改写。
- 不把现有 Skill 迁移成知识库条目，不通过知识库发布状态控制 Skill 生效。
- 继续以 `find_data_skills` 作为权威选择入口，不新增并行 Skill 选择服务或第二套选择开关。
- 个人空间 Skill 仅创建者可见、可编辑和可使用；工作空间 Skill 仅当前工作空间可用；平台公共 Skill 仍需经过使用方上下文校验。

### 2.3 已有事件和 JSON 字典

现有代码：

- `backend/apps/system/models/tenant.py`
- `backend/apps/system/schemas/tenant_schema.py`
- `backend/apps/system/crud/tracking_config.py`
- `backend/apps/system/crud/tracking_expression.py`
- `backend/apps/system/crud/tracking_excel.py`
- `backend/apps/system/api/tracking_config.py`
- `frontend/src/views/system/data-dictionary/DataDictionary.vue`

已有能力：

- `sys_tenant_tracking_config`、`sys_tenant_tracking_table`、`sys_tenant_tracking_field` 和事件分组表。
- 字段支持 `source_field`、`json_path`、`expression`、`semantic_type`、枚举和更新方式。
- 工作空间与当前绑定数据源隔离。
- Excel 模板、导入、导出和物理 Schema 校验。
- 能生成 Smart Q&A 和 AI 看板使用的 tracking prompt context。

主要缺口：

- 只有工作空间结构，没有平台公共事件/JSON 结构化记录。
- 当前 PUT 和 Excel 导入会直接修改生效配置。
- 无逐条草稿、发布、版本和回滚。
- 事件名称映射部分以聚合 JSON 保存，缺少知识条目级版本关联。

### 2.4 已有统一 SQL 上下文

`backend/apps/datasource/crud/sql_engine.py` 中的 `BusinessSqlContextService` 已完成：

1. 当前数据源读取和访问校验。
2. Data Skills 选择。
3. 权限过滤后的 AI Schema 和允许表。
4. 工作空间事件/JSON 字典上下文。
5. 上下文哈希和快照元数据。

这是知识库运行时的核心接入点。当前 `semantic_context` 只包含 `tracking_config` 和 `data_skill`，尚无知识检索内容、引用、知识版本和检索告警。

### 2.5 四条消费链

1. Smart Q&A：`backend/apps/chat/task/llm.py` 和 `smart_qa_graph.py` 已部分复用 `BusinessSqlContextService`。
2. AI 看板 SQL：`backend/apps/dashboard/crud/ai_sql_generator.py` 的 `collect_context` 节点已复用统一 SQL 上下文。
3. 综合分析助手：`backend/apps/analysis_assistant/api/analysis_assistant.py` 主聊天链已复用统一 SQL 上下文和上下文快照。
4. 看板报告解读：仍通过 `_collect_data_skill_context` 和 `_collect_tracking_context` 旁路加载，并把异常捕获后返回空字符串。

报告解读旁路必须移除，否则知识权限、版本、告警和引用无法与其他入口保持一致。

### 2.6 可复用基础设施

- `EmbeddingModelCache` 已支持 OpenAI-compatible `text-embedding-v4`。
- `pgvector>=0.4.1` 已在后端依赖中。
- 历史迁移已创建 vector extension，但旧 terminology/data_training 表已删除。
- Redis task queue 已具备租户边界、去重、重试和本地独立队列。
- `chat_record.agent_context_snapshot` 已能保存 Smart Q&A 上下文快照。

## 3. 技术方案选择

### 3.1 方案 A：全部资产并入知识库

做法：把普通文档、事件、JSON 映射和 Skills 都转换为知识库条目，统一经过知识发布流程。

问题：

- Skills 的启停、版本、个人作用域和自动匹配会与知识内容发布状态混淆。
- 会改变现有 Skills 页面、API、存储及调用权威性，第一阶段回归面过大。
- 纯知识条目不能替代 Skill 的触发、流程和结果约束能力。

不采用。

### 3.2 方案 B：知识库与 Skills 独立治理、运行时融合

做法：知识库负责四类知识的条目、版本、发布、切片和权限；Skills 继续使用现有主数据、管理入口和 `find_data_skills` 选择链路。运行时由 `BusinessSqlContextService` 调用现有 Skill 选择逻辑，再由 `BusinessSemanticContextService` 合并结构化知识、文档 RAG 和 Skill 规则。

优点：

- 满足知识内容统一管理和版本要求，同时保留 Skills 的独立生命周期。
- 最大限度复用当前 SQL 校验、tracking 表达式和前端图表字段能力。
- 不引入当前项目不存在的 Skill 与助手绑定模型，也不删除现有 `data_skill_id` 显式选择能力。
- 可以渐进接入，不要求第一阶段改写旧 Skills 逻辑。

成本：

- 需要在不改变现有选择语义的前提下补充权限快照、知识融合和调用审计。
- 统一上下文必须复用一次 `find_data_skills` 结果，避免各场景重复查询或重新匹配。

推荐采用。

### 3.3 方案 C：继续由各 AI 场景分别加载

做法：知识库和 Skills 继续保持现状，各 AI 场景自行检索知识和匹配 Skill。

问题：

- 权限、版本、告警和引用会继续分散。
- 同一用户在不同 AI 场景可能命中不同的知识与 Skills。
- 难以统一实施事件、Schema 和数据权限的召回前过滤。

第一期不采用。

## 4. 总体架构

```mermaid
flowchart LR
    UI["知识库管理页面"] --> API["KnowledgeBase API"]
    SKILLUI["现有 Skills 管理页面"] --> SKILLSTORE["现有 custom_prompt / embedding"]
    API --> VERSION["条目/草稿/版本服务"]
    VERSION --> VALIDATE["类型校验器"]
    VALIDATE --> PUBLISH["单条发布服务"]
    PUBLISH --> WORKER["Redis Worker"]
    WORKER --> NORMALIZE["标准化与切片"]
    NORMALIZE --> EMBED["Embedding"]
    EMBED --> STORE["PostgreSQL + pgvector"]

    AUTH["用户/工作空间/数据源/元数据权限"] --> PERMISSION["PermissionScopeService"]
    PERMISSION --> CTXBUILD["BusinessSqlContextService.build"]
    CTXBUILD --> SELECT["现有 find_data_skills"]
    SKILLSTORE --> SELECT
    STORE --> RETRIEVE["KnowledgeRetrievalService"]
    PERMISSION --> RETRIEVE
    SELECT --> SEMANTIC
    RETRIEVE --> SEMANTIC
    TRACKING["现有 Tracking 运行服务"] --> SEMANTIC["BusinessSemanticContextService"]
    SEMANTIC --> SQLCTX["BusinessSqlContext"]
    SQLCTX --> SMART["Smart Q&A"]
    SQLCTX --> DASH["AI 看板 SQL"]
    SQLCTX --> ANALYSIS["综合分析助手"]
    SEMANTIC --> REPORT["看板问答/报告解读"]
    SQLCTX --> POSTCHECK["SQL AST + 权限后置校验"]
```

架构边界：

- 知识库与 Skills 独立存储、独立管理、独立生命周期；本期不新增 Skill 与助手绑定表。
- `PermissionScopeService` 是两类资产进入运行时之前的共同权限入口。
- 现有 `find_data_skills` 是 Skill 选择的权威入口，保留用户指定和自动匹配两种模式。
- `KnowledgeRetrievalService` 同时支持结构化精确查询和文档语义检索。
- `BusinessSemanticContextService` 负责融合，不负责扩大权限；最终上下文始终是各权限集合的交集。
- SQL 生成前过滤无权元数据，生成后使用 AST 再次验证实际引用对象并注入既有行级权限规则。

## 5. 数据模型

### 5.1 `knowledge_base`

保留现有表作为知识主记录，新增：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `knowledge_type` | varchar(32) | DOCUMENT/BUSINESS/EVENT/JSON_FIELD |
| `stable_key` | varchar(255) | 作用域内稳定标识 |
| `draft_version_id` | bigint nullable | 当前草稿版本 |
| `current_version_id` | bigint nullable | 当前发布版本 |
| `publishing_version_id` | bigint nullable | 当前正在发布的版本，同一条目同时最多一个 |
| `archived` | boolean | 是否归档 |
| `update_by` | bigint nullable | 最后修改人 |
| `publish_by` | bigint nullable | 最后发布人 |
| `publish_time` | timestamp nullable | 最后发布时间 |

保留 `tenant_id` 和 `visibility_scope`：

- 平台公共条目使用 `PLATFORM_PUBLIC` 和系统默认平台 tenant。
- 工作空间条目使用 `ADMIN_PUBLIC` 和当前 tenant。

唯一约束：

```text
(tenant_id, visibility_scope, stable_key)
```

现有 `content`、`file_id`、`file_name` 和 `file_ext` 在兼容期保留，只作为旧数据迁移来源；运行时改读当前发布版本。

### 5.2 `knowledge_base_version`

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `id` | bigint | 主键 |
| `knowledge_base_id` | bigint | 知识条目 |
| `tenant_id` | bigint | 冗余租户边界 |
| `version_number` | integer | 条目内递增版本 |
| `revision` | integer | 草稿乐观锁版本，每次成功保存递增 |
| `status` | varchar(32) | 版本状态 |
| `payload` | jsonb | 四类知识的结构化内容 |
| `normalized_content` | text | 发布时生成的 RAG 标准文本 |
| `validation_report` | jsonb | 错误、警告和 Schema 校验结果 |
| `content_hash` | varchar(64) | payload 与正文的 SHA-256 |
| `file_id/file_name/file_ext` | varchar | 普通文档源文件 |
| `parser_version` | varchar(64) | 文档解析器版本 |
| `create_by/create_time` | bigint/timestamp | 草稿审计 |
| `publish_by/publish_time` | bigint/timestamp | 发布审计 |
| `error_message` | text | 发布失败原因 |

唯一约束：`(knowledge_base_id, version_number)`。

### 5.3 `knowledge_base_chunk`

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `id` | bigint | 主键 |
| `knowledge_base_id` | bigint | 条目 ID |
| `version_id` | bigint | 发布版本 |
| `tenant_id` | bigint | 租户边界 |
| `visibility_scope` | varchar(32) | 平台或工作空间 |
| `chunk_index` | integer | 版本内顺序 |
| `section_path` | text | 标题或结构化路径 |
| `content` | text | 切片内容 |
| `token_count` | integer | token 估算 |
| `content_hash` | varchar(64) | 切片哈希 |
| `embedding_model` | varchar(255) | 模型名 |
| `embedding_signature` | varchar(128) | 模型、配置和维度签名 |
| `embedding_dimension` | integer | 实际维度 |
| `embedding` | vector | pgvector 向量 |
| `create_time` | timestamp | 创建时间 |

第一期使用严格范围过滤后的精确向量距离查询，不预设 `text-embedding-v4` 维度，也不在迁移中创建猜测维度的 HNSW 索引。上线测得稳定维度后再单独增加索引迁移。

### 5.4 `knowledge_base_workspace_override`

保存工作空间对平台知识的启停：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `tenant_id` | bigint | 工作空间 |
| `knowledge_base_id` | bigint | 平台知识 |
| `enabled` | boolean | 当前工作空间是否启用 |
| `reason` | text | 操作原因 |
| `update_by/update_time` | bigint/timestamp | 审计 |

唯一约束：`(tenant_id, knowledge_base_id)`。

### 5.5 `knowledge_base_applicability`

缓存平台结构化知识对使用方数据源的物理适用性，不缓存用户授权结论：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `knowledge_base_id/version_id` | bigint | 平台知识版本 |
| `tenant_id/datasource_id` | bigint | 使用方上下文 |
| `physical_schema_hash` | varchar(64) | 数据源物理 Schema 指纹 |
| `status` | varchar(32) | VALID/INVALID/STALE/ERROR |
| `report` | jsonb | 缺表、缺字段、方言或 JSON Path 问题 |
| `checked_at` | timestamp | 校验时间 |

唯一约束：`(version_id, tenant_id, datasource_id, physical_schema_hash)`。

Schema 或工作空间绑定变化时，旧记录因 `physical_schema_hash` 不匹配自然失效。用户级事件、Schema、表、字段和 JSON Path 权限不写入该表，每次请求通过 `PermissionScopeSnapshot` 过滤。

### 5.6 `knowledge_base_source_reference`

只读记录知识条目与现有配置来源的关联，用于去重、追踪和并行接入；不得通过该关联反向写入现有配置：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `knowledge_base_id/version_id` | bigint | 知识条目和版本 |
| `source_type` | varchar(32) | TRACKING_CONFIG/TRACKING_TABLE/TRACKING_FIELD |
| `source_id` | bigint | 现有权威来源记录 ID |
| `source_hash` | varchar(64) | 来源内容哈希 |
| `sync_mode` | varchar(16) | 第一阶段固定 READ_ONLY |

唯一约束：`(knowledge_base_id, source_type, source_id)`。

### 5.7 `knowledge_retrieval_log`

保存无敏感正文的检索审计：

- request ID、surface、tenant ID、datasource ID。
- query hash，不保存完整用户问题。
- 命中的知识、版本、切片、得分和耗时。
- 模型签名、降级告警和失败类型。
- 创建时间。

### 5.8 `semantic_context_audit`

保存一次统一调用实际采用的权限快照、知识和 Skills，不保存敏感正文：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `request_id` | varchar(64) | 单次 AI 请求标识 |
| `tenant_id/user_id/datasource_id` | bigint | 运行边界 |
| `surface` | varchar(64) | Smart Q&A、看板 SQL、看板问答或综合分析助手 |
| `permission_version` | varchar(128) | 权限版本或指纹 |
| `schema_hash` | varchar(64) | 授权后 Schema 指纹 |
| `knowledge_snapshot` | jsonb | 条目、版本、切片和适用性结果 |
| `skill_snapshot` | jsonb | Skill ID、作用域、场景、显式/自动选择模式和选择结果 hash |
| `warnings` | jsonb | 检索、权限、冲突和降级告警 |
| `create_time` | timestamp | 创建时间 |

该表用于审计和问题复现，不作为运行主数据。用户无权查看的 Skill 或知识不得出现在快照中。

### 5.9 元数据权限扩展

现有 `ds_rules` 已维护平台/工作空间作用域、用户列表和白名单，`ds_permission` 已维护具体权限记录。优先复用这套规则绑定关系，不新增另一套用户授权表。

扩展 `ds_permission.type`：

| 类型 | `ds_id` | `table_id` | `permissions` 内容 |
| --- | --- | --- | --- |
| `schema` | 必填 | 空 | Catalog/Schema 稳定键及 `enable` |
| `event` | 必填 | 事件物理表，可空 | 工作空间事件名、事件定义稳定 ID 及 `enable` |
| `event_property` | 必填 | 属性来源表，可空 | 事件名、属性稳定键、来源字段/JSON Path 及 `enable` |

约束：

- `apps.datasource.api.permission.PERMISSION_TYPES` 增加 `schema`、`event`、`event_property`。
- `schema` 记录必须校验目标属于当前数据源的物理元数据或工作空间 Schema 元数据。
- `event`、`event_property` 必须校验目标属于当前工作空间 tracking 规范，不能用表名给同名事件做命名空间。
- 继续由 `ds_rules.permission_list`、`user_list` 和 `white_list_user` 决定规则对哪些用户生效。
- 第一阶段采用现有“禁止型”权限语义；没有独立事件权限记录时按 8.5 节继承物理对象权限。
- 平台权限记录可以被工作空间读取但不能修改；服务端仍从当前用户上下文确定作用域。

## 6. 四类知识 Payload 与独立 Skills 模型

在 `backend/apps/knowledge_base/schemas.py` 使用带 `knowledge_type` 判别字段的 Pydantic union。

### 6.1 普通知识文档

```python
class DocumentPayload(BaseModel):
    knowledge_type: Literal["DOCUMENT"]
    markdown: str
    tags: list[str] = Field(default_factory=list)
```

上传 Word 时先解析为 Markdown/标准文本并保存到草稿 payload；源文件信息保存在版本表。

### 6.2 业务知识

```python
class BusinessSqlExample(BaseModel):
    name: str
    question: str
    sql: str
    dialect: str | None = None
    notes: str = ""


class BusinessKnowledgePayload(BaseModel):
    knowledge_type: Literal["BUSINESS"]
    term: str | None = None
    aliases: list[str] = Field(default_factory=list)
    definition: str = ""
    formula: str = ""
    constraints: list[str] = Field(default_factory=list)
    related_objects: list[dict[str, str]] = Field(default_factory=list)
    examples: list[BusinessSqlExample] = Field(default_factory=list)
```

校验规则：`term/definition` 或至少一条带 question 和 SQL 的示例必须存在。

### 6.3 事件参数对照

```python
class EventParameter(BaseModel):
    name: str
    display_name: str = ""
    data_type: str
    required: bool = False
    description: str = ""
    value_mappings: dict[str, str] = Field(default_factory=dict)


class EventKnowledgePayload(BaseModel):
    knowledge_type: Literal["EVENT"]
    event_name: str
    display_name: str = ""
    aliases: list[str] = Field(default_factory=list)
    description: str = ""
    table_name: str
    event_name_field: str
    event_time_field: str | None = None
    parameters: list[EventParameter] = Field(default_factory=list)
```

同一工作空间跟踪规范内 `event_name` 唯一，不以表名作为事件命名空间。

### 6.4 JSON 字段解析

```python
class JsonFieldKnowledgePayload(BaseModel):
    knowledge_type: Literal["JSON_FIELD"]
    schema_name: str | None = None
    table_name: str
    source_field: str
    json_path: str
    field_name: str
    display_name: str = ""
    data_type: str
    expression: str
    aliases: list[str] = Field(default_factory=list)
    description: str = ""
    value_mappings: dict[str, str] = Field(default_factory=dict)
```

### 6.5 Skills 独立模型

Skills 继续使用现有 `custom_prompt.type=DATA_SKILL` 及其 embedding、作用域、启停和 SQL 规则字段。第一阶段不新增知识库 `DATA_SKILL` payload，也不迁移或复制 Skill 主数据。

统一上下文保留现有 Skill 选择结果，不再定义第二套路由权威模型。建议只增加审计快照：

```python
@dataclass(frozen=True)
class SelectedSkillSnapshot:
    skill_id: int
    visibility_scope: Literal["PLATFORM_PUBLIC", "ADMIN_PUBLIC", "USER_PRIVATE"]
    tenant_id: int | None
    target_scope: Literal["SMART_QA", "ANALYSIS_ASSISTANT", "REPORT_INTERPRETATION", "ALL"]
    selection_mode: Literal["EXPLICIT", "AUTO"]
    datasource_scoped: bool
    required_tables_hash: str | None
```

作用域规则：

- 平台公共 Skill：平台维护；候选进入当前工作空间时还需校验当前数据源、事件和 Schema 权限。
- 工作空间 Skill：`tenant_id` 必须等于当前工作空间，只对其成员开放。
- 个人空间 Skill：`owner_user_id` 必须等于当前用户，仅创建者可查看、编辑和使用。
- 沿用 `_dedupe_overridden_data_skills` 的同类 Skill 覆盖/去重语义，不在知识库接入中重新定义优先级。
- 个人和工作空间 Skill 可以补充任务规则，但不能覆盖平台安全规则或扩大任何数据权限。
- 第一阶段沿用现有生效状态；后续若增加 Skill 发布/审批，必须作为 Skills 自身生命周期实现，不复用知识库发布状态机。

## 7. 草稿、校验和发布状态机

### 7.1 状态枚举

```text
DRAFT
VALIDATING
VALIDATION_FAILED
READY_TO_PUBLISH
PUBLISHING
PUBLISHED
PUBLISH_FAILED
SUPERSEDED
ARCHIVED
```

### 7.2 保存草稿

1. 校验用户对条目作用域的管理权限。
2. 新条目创建主记录和 version 1；已有条目更新当前草稿或创建新草稿版本。
3. 更新草稿必须携带读取时获得的 `draft_version_id` 和 `revision`，使用条件更新保证版本一致。
4. 条件更新成功后 `revision + 1` 并重新计算 `content_hash`。
5. revision 不一致时返回 HTTP 409，机器码为 `KNOWLEDGE_DRAFT_CONFLICT`，中文消息为“该知识已被其他用户更新，请刷新后重新编辑。”，不得覆盖对方内容。
6. 保存后状态为 `DRAFT`，不改变 `current_version_id`；已发布条目的线上内容继续使用当前发布版本。

### 7.3 校验

通用校验：

- 必填字段、stable key、类型、作用域和 payload 格式。
- 同作用域唯一性。
- 工作空间 stable key/名称与平台知识冲突。
- 引用的平台知识存在且已发布。

类型校验：

- 文档：正文非空、文件可解析。
- 业务知识：定义或 SQL 示例至少存在一项；SQL 只读且可被 sqlglot 解析。
- 事件：事件唯一、物理表和事件名字段存在。
- JSON：宿主字段、JSON Path、目标类型和确定性 expression 有效。

工作空间结构化知识在发布前校验当前绑定数据源。平台结构化知识在平台发布时做格式和方言校验，在每个使用方工作空间首次使用或 Schema 变化后再做数据源适用性校验。

### 7.4 发布

`POST /knowledge-base/{id}/publish` 只接受 `READY_TO_PUBLISH` 的当前草稿，并把 `version_id`、`revision`、`tenant_id`、`content_hash` 放入 Redis 任务。Worker 执行：

```text
取得租户隔离的条目级发布锁
  -> 再次确认草稿 ID、revision、content_hash 和 PUBLISHING 状态
  -> 解析/标准化
  -> 切片
  -> 批量生成 embedding
  -> 校验向量数量和维度
  -> 数据库事务写入切片
  -> current_version_id 原子切换
  -> 旧版本标记 SUPERSEDED
  -> 新版本标记 PUBLISHED
```

Embedding 是外部调用，不能持有数据库事务等待。向量先在事务外生成，最终版本切换在短事务内完成。

发布锁名称必须通过 `tenant_redis_key(tenant_id, "knowledge_base", knowledge_base_id, "publish")` 构造，再交给现有 Redis 锁能力；锁使用有限 TTL 和持有者 token，数据库中的 `publishing_version_id`、版本状态和条件更新仍是最终权威。重复发布同一 version/revision/content hash 时返回已有任务，不重复入队。

失败规则：

- 版本标记 `PUBLISH_FAILED`，记录失败阶段和安全错误信息。
- `current_version_id` 不变。
- 不删除旧切片。
- 相同 `content_hash` 和 embedding signature 可以复用已生成向量。

### 7.5 回滚

回滚不是直接修改 `current_version_id`。系统复制目标历史版本形成新草稿，重新校验和发布，从而保留完整审计链。

### 7.6 同一知识条目的并发控制

- 第一期同一知识条目只允许一个可编辑草稿；编辑页面不持有长期锁，保存时使用 `revision` 乐观锁检测冲突。
- 两个用户同时编辑时，先保存者成功；后保存者收到 `KNOWLEDGE_DRAFT_CONFLICT` 和中文提示，前端保留本地内容并要求刷新后人工合并，不自动覆盖或静默合并。
- 上传文件先写入本次请求独立的临时文件；数据库条件更新成功后再绑定到草稿版本，冲突或异常时清理临时文件，不能删除或替换其他请求已保存的源文件。
- 校验和发布绑定确定的 `draft_version_id + revision + content_hash`；任一值变化后，旧校验结果和旧发布任务均不得切换当前版本。
- 同一条目处于 `PUBLISHING` 时，保存、重新校验、再次发布、删除、归档和回滚均返回 HTTP 409，机器码为 `KNOWLEDGE_PUBLISHING`，中文消息为“该知识正在发布中，请稍后再试。”。
- Worker 最终切换使用数据库条件更新；只有 `publishing_version_id`、version status、revision 和 content hash 全部匹配时才能更新 `current_version_id`。过期 Worker 只记录审计告警，不得覆盖更新结果。
- Redis 锁过期、Worker 重启或多后端实例竞争时，以数据库状态为准；任务超时后按发布失败流程释放 `publishing_version_id`，旧发布版本继续可用。

## 8. 权限、作用域和冲突

### 8.1 管理权限

- 全局平台管理员管理 `PLATFORM_PUBLIC`。
- 工作空间管理员管理当前 tenant 的 `ADMIN_PUBLIC`。
- 普通成员只查看权限允许的已发布知识。
- 服务端从 `CurrentUser/CurrentTenant` 计算 tenant，不接受客户端指定任意 tenant ID。

### 8.2 工作空间停用平台知识

`PUT /knowledge-base/{id}/workspace-enabled` 只允许当前工作空间管理员操作平台条目。禁用记录在知识检索和 tracking 组合阶段都必须生效。

### 8.3 冲突规则

- 工作空间不能编辑平台记录。
- 同 stable key 或归一名称冲突阻止工作空间发布。
- 补充说明通过显式 `platform_knowledge_id` 引用平台知识，不能复制并覆盖平台 payload。
- 不通过优先级或相似字段静默解决冲突。

### 8.4 Skills 管理权限

| 作用域 | 查看和使用 | 创建/编辑 | 启停/删除 |
| --- | --- | --- | --- |
| 平台公共 | 平台授权用户；运行时仍按当前上下文裁剪 | 平台管理员 | 平台管理员 |
| 工作空间 | 当前工作空间成员 | 现有工作空间 Skill 管理权限 | 创建者或工作空间管理员，遵循现有规则 |
| 个人空间 | 仅创建者 | 仅创建者 | 仅创建者 |

平台管理员可审计或处置违规个人 Skill，但不得把“平台管理员身份”作为日常读取或修改个人 Skill 内容的默认授权。

### 8.5 元数据与数据权限

当前代码可直接复用的数据权限能力包括：

- `apps.datasource.crud.permission.has_datasource_access`：数据源访问。
- `get_ai_table_schema`：按当前工作空间字典或缓存元数据生成授权后的 AI Schema 和允许表。
- `get_column_permission_scope`：字段权限和 `denied_json_paths`。
- `get_row_permission_filters`、`get_applicable_row_permission_constraints`：行权限。
- `sql_engine_executor` 和 `sql_permission`：执行前表、字段、JSON Path 及行权限校验/改写。

当前仓库未发现独立的 Catalog/Schema 权限类型或事件/事件属性权限模型。第一阶段实现必须补充这两类元数据授权能力，或者在产品未开启独立事件权限时，显式采用“事件权限继承其物理表、事件字段及参数字段权限”的策略；不得把尚不存在的事件权限校验伪装成已实现能力。

最终可用范围必须按交集计算：

```text
工作空间访问权
∩ 当前数据源访问权
∩ Catalog/Schema 权限
∩ 表权限
∩ 字段权限
∩ JSON 宿主字段与路径权限
∩ 事件、事件属性和公共/用户属性权限
∩ 行级过滤与字段脱敏规则
∩ 知识及 Skill 作用域
```

规则：

- 无 Schema 权限时，不返回该 Schema 的表、字段、事件映射和引用它们的 SQL 示例。
- 无表权限时，不召回引用该表的业务知识，也不加载引用该表的 Skill 规则。
- 无字段权限时，不向模型暴露字段名、字段说明或示例值。
- JSON Path 至少继承宿主字段权限；存在路径级权限时继续取路径权限交集。
- 无事件权限时，不召回对应事件、事件参数、事件属性及引用它们的知识和 Skill。
- 一条 SQL 示例或 Skill 引用多个对象时，所有对象都通过校验后才可进入上下文。
- 行级权限和脱敏规则不写入检索正文，只在 SQL 规划、验证和执行阶段由现有权限服务强制实施。
- 页面权限与运行时权限必须使用同一服务端策略，不能依赖前端隐藏按钮。

### 8.6 两阶段权限校验

1. 召回前：生成授权后的 Schema、事件和属性集合，并在数据库/查询层过滤知识与 Skills，避免无权元数据进入 Prompt。
2. 生成后：使用 SQL AST 重新验证实际 Schema、表、字段和 JSON 表达式，再执行只读、安全、行级过滤和脱敏检查。

权限缓存键至少包含 `tenant_id`、`user_id`、`datasource_id`、`permission_version` 和 `schema_hash`。权限、事件字典、Schema 或工作空间数据源绑定变化时必须失效。

第一阶段权限扩展建议：

- 数据源只有一个有效业务 Schema 时，Schema 访问继承数据源访问并继续受表/字段权限约束。
- 数据源暴露多个 Catalog/Schema 时，新增明确的 Schema 允许/禁止记录，禁止仅靠名称过滤。
- 新增事件权限记录时以 `tenant_id + datasource_id + event_name` 标识事件，以事件属性稳定键标识属性；事件名仍只在当前工作空间跟踪规范内唯一。
- 事件无独立权限配置时，继承事件物理表、事件名字段及参数来源字段权限；任一必需对象无权即判定事件不可用。
- `PermissionScopeSnapshot.permission_version` 必须纳入权限规则更新时间、tracking 版本和用户角色版本，保证权限变化使缓存失效。

## 9. 平台知识动态适用性

平台知识可以包含具体物理表、字段、JSON Path 和 SQL，但不固定绑定某个工作空间数据源。

`KnowledgeApplicabilityService.evaluate(...)` 接口：

```python
@dataclass
class KnowledgeApplicabilityResult:
    valid: bool
    physical_schema_hash: str
    errors: list[str]
    warnings: list[str]


class KnowledgeApplicabilityService:
    @staticmethod
    def evaluate(
        *,
        session,
        current_user,
        tenant_id: int,
        datasource_id: int,
        version_id: int,
        physical_schema: str,
    ) -> KnowledgeApplicabilityResult: ...
```

校验对象：

- EVENT：表、事件名字段、事件时间字段和参数来源。
- JSON_FIELD：表、宿主字段、JSON Path 格式、表达式方言。
- BUSINESS：SQL 示例中的表、字段、权限和只读性。
- DOCUMENT：不做物理对象校验。

只有物理适用性为 valid 且通过当前用户 `PermissionScopeSnapshot` 授权过滤的平台结构化知识，才能进入当前请求的结构化 SQL 上下文和 RAG 候选集。invalid 原因进入管理页和 `retrieval_warnings`，不能改用相似字段。

物理适用性缓存按 version、tenant、datasource 和 physical schema hash 判断。首次使用、缓存缺失或记录 stale 时，请求内立即执行一次适用性校验并写入缓存；校验异常形成明确 warning，不把“尚未缓存”当成“不适用”。用户授权结果只在当前权限版本范围内短期缓存，键中必须包含 user ID 和 permission version。

## 10. 现有运行服务兼容与并行融合

### 10.1 Data Skills

第一阶段保留 `custom_prompt` 作为 Skills 权威主数据，不创建知识库运行投影：

- `frontend/src/views/data-skills/index.vue`、现有 API、`custom_prompt` 存储、启停、SQL 校验和既有匹配逻辑保持不变。
- `find_data_skills` 继续负责候选查询、作用域过滤、用户启停、数据源/必需表校验、覆盖去重和问题匹配。
- 用户传入 `data_skill_id` 时沿用显式选择分支；未传入时沿用 embedding 排序并在失败时按关键词排序。
- 候选集合继续是可用的平台公共 Skills、当前工作空间 Skills、当前用户的个人空间 Skills。
- 个人空间 Skill 必须按 `user_id` 过滤；工作空间 Skill 必须按 `tenant_id` 过滤；平台 Skill 必须对当前数据源和授权元数据执行适用性校验。
- 继续复用现有 `_data_skill_sql_validation_violation`，但生成 SQL 前后都使用同一组选中 Skills。
- 自动匹配继续保留 foundation Skills，并沿用当前最多 12 条的限制。
- `BusinessSqlContextService.build` 只调用一次 `find_data_skills`，统一上下文复用该结果，不建立新旧两条并行 Skill 路径。
- 当前三元组返回值保持兼容；为审计新增可选的结构化选择元数据接口或内部结果对象，再由原 `find_data_skills` 适配回 `(content, prompt_list, ai_model_id)`，不得让调用方重新查询和猜测 Skill ID。
- 知识库接入只扩展选择结果的权限快照、知识上下文融合和审计，不改变 `data_skill_id`、`target_scope`、三级作用域及现有覆盖规则。

### 10.2 工作空间事件和 JSON

第一阶段现有 `sys_tenant_tracking_*` 和数据字典仍是旧调用链的权威来源；知识库发布 EVENT/JSON_FIELD 不更新这些表。

- `BusinessSemanticContextService` 分别读取现有 tracking 配置和已发布知识条目。
- 若知识条目通过 `knowledge_base_source_reference` 引用了现有 tracking 记录，则按来源 ID 去重，不重复向 Prompt 注入相同定义。
- 若两边是独立记录但 stable key、事件名或物理路径冲突，统一上下文构建失败并返回明确冲突，不静默选取其中之一。
- 原数据字典页面、Excel 导入和现有 tracking API 保持原行为。

### 10.3 平台事件和 JSON

平台 EVENT/JSON_FIELD 不预先复制到所有 tenant：

1. 从知识版本读取平台结构化 payload。
2. 针对当前 tenant/datasource 校验适用性。
3. 把 valid 平台字段组合成临时 `TenantTrackingConfigDTO` 片段。
4. 与现有工作空间 tracking 上下文组合。
5. 发现同名/同 stable key 冲突时返回配置错误，不覆盖工作空间记录。

第一阶段只让统一 AI 上下文使用组合结果，不修改 `/system/tracking-config/event-catalog` 和原数据字典页面行为。后续若要让前端字段选择器也显示知识库事件，需要另行评审兼容和冲突策略。

### 10.4 现有页面兼容

- 第一阶段不跳转、不只读、不删除现有 Skills 和数据字典页面。
- 现有 Skills 写入仍直接维护 `custom_prompt`，不会创建或修改知识库条目。
- 现有数据字典写入和 Excel 导入仍按当前逻辑维护 tracking 配置。
- 新知识库页面并行提供事件和 JSON 知识管理；在启用运行融合前，通过来源标识和稳定 ID 避免与现有 tracking 配置重复加载。
- 后续是否统一旧写入口需要单独迁移方案和用户确认，不属于本开发文档第一阶段。

## 11. 文档解析、标准化和切片

### 11.1 解析

- Markdown：UTF-8-SIG/UTF-8。
- Word：保留现有 XML 解析，补充标题样式和表格提取；不执行宏或外部链接。
- 在线 Markdown 与文件上传最终都写入版本 payload。

### 11.2 标准化

每种类型生成稳定文本：

- DOCUMENT：标题路径 + 正文。
- BUSINESS：术语、别名、定义、约束、关联对象、问题和 SQL 示例。
- EVENT：事件定义 + 每个参数的独立段落。
- JSON_FIELD：物理位置、JSON Path、表达式、类型和业务说明。

标准文本包含知识类型和作用域标签，但不包含数据库密码、文件路径或内部权限数据。

### 11.3 切片

- Markdown 按 H1/H2/H3 和长度递归切分。
- SQL 代码块、表格和紧邻说明保持在同一切片。
- EVENT 可按事件概要和参数组切片。
- BUSINESS 可按定义和 SQL 示例切片。
- 超长段落按 token 预算切分并保留少量重叠。

## 12. RAG 检索服务

### 12.1 接口

```python
@dataclass
class KnowledgeCitation:
    knowledge_id: int
    version_id: int
    chunk_id: int
    knowledge_type: str
    scope: str
    name: str
    section_path: str
    score: float


@dataclass
class KnowledgeRetrievalResult:
    context: str
    citations: list[KnowledgeCitation]
    version_hash: str | None
    warnings: list[str]


class KnowledgeRetrievalService:
    @staticmethod
    def search(
        *,
        session,
        current_user,
        tenant_id: int,
        datasource_id: int,
        surface: str,
        query: str,
        schema: str,
        allowed_tables: list[str],
        top_k: int,
        max_context_chars: int,
    ) -> KnowledgeRetrievalResult: ...
```

`surface` 仅用于构造检索查询、上下文预算和审计；第一期不按场景过滤知识。

检索前由 `PermissionScopeService` 生成授权快照：

```python
@dataclass(frozen=True)
class PermissionScopeSnapshot:
    tenant_id: int
    user_id: int
    datasource_id: int
    permission_version: str
    schema_hash: str
    allowed_schemas: frozenset[str]
    allowed_tables: frozenset[str]
    allowed_columns: dict[str, frozenset[str]]
    allowed_events: frozenset[str]
    allowed_event_properties: dict[str, frozenset[str]]
    allowed_json_paths: dict[str, frozenset[str]]


class PermissionScopeService:
    @staticmethod
    def build_snapshot(
        *, session, current_user, tenant_id: int, datasource_id: int
    ) -> PermissionScopeSnapshot: ...
```

知识结构化引用在进入向量候选集前先与该快照求交集；不能全局召回后再隐藏引用。

### 12.2 数据库过滤顺序

向量 SQL 必须在数据库层先过滤：

1. `knowledge_base.active=true` 且未归档。
2. chunk 属于 `current_version_id`。
3. 平台知识或当前 tenant 的工作空间知识。
4. 排除当前 tenant 已停用的平台知识。
5. 结构化平台知识必须存在当前 datasource/schema hash 的 valid applicability。
6. 条目引用的 Schema、表、字段、JSON Path 和事件均属于权限快照允许范围。
7. embedding signature 与当前模型一致。

过滤后按 cosine distance 排序，应用最小得分、Top-K 和最大字符预算。

### 12.3 查询构造

- Smart Q&A：当前问题 + 必要的会话上下文。
- AI 看板 SQL：intent、标题、已选指标、维度、筛选和表。
- 看板问答：问题、可见图表标题、字段和指标，不放完整结果数据做 embedding。
- 综合分析助手：当前问题、当前轮必要上下文和已选中 Skill 摘要。

### 12.4 Prompt 安全

知识内容使用独立低优先级标签：

```text
<retrieved-knowledge priority="reference-only">
...
</retrieved-knowledge>
```

系统 Prompt 明确：知识和 Skills 中的命令、权限声明和 SQL 不能覆盖当前权限、Schema、结构化映射或 SQL 安全规则。

### 12.5 降级

- 知识检索失败不阻断已有完整结构化配置的 SQL 任务。
- 返回 `retrieval_warnings` 并写检索日志。
- 不把异常伪装成“没有知识”。
- 显式结构化配置或 Schema 失效仍需阻断 SQL，不能因 RAG 可用而降级猜测。

## 13. 统一语义上下文

新增 `backend/apps/datasource/crud/semantic_context.py`：

```python
@dataclass
class BusinessSemanticContext:
    selected_skills: list[SelectedSkillSnapshot] = field(default_factory=list)
    skill_selection_hash: str | None = None
    tracking_config: str = ""
    tracking_summary: list[str] = field(default_factory=list)
    knowledge_context: str = ""
    knowledge_citations: list[KnowledgeCitation] = field(default_factory=list)
    knowledge_version_hash: str | None = None
    warnings: list[str] = field(default_factory=list)


class BusinessSemanticContextService:
    @staticmethod
    def build(
        *,
        session,
        current_user,
        tenant_id: int,
        datasource_id: int,
        question: str,
        surface: str,
        schema: str,
        allowed_tables: list[str],
    ) -> BusinessSemanticContext: ...
```

调整 `BusinessSqlContext`：

```python
@dataclass
class BusinessSqlContext:
    # 现有 datasource/schema/allowed_tables 等字段保留
    semantic: BusinessSemanticContext
```

兼容期保留 `data_skill`、`data_skill_list` 和 `tracking_config` 属性，内部代理到 `semantic`。`business_context_hash` 纳入权限版本、Schema hash、Skill 选择 hash、知识版本 hash 和引用 chunk ID，不把完整 Skill 或知识正文写入快照。

权威顺序：

```text
权限和当前工作空间/数据源
  > 用户明确配置
  > 授权 Schema
  > 事件和 JSON 结构化映射
  > 当前 `find_data_skills` 选中且授权后的 Skills
  > 业务知识和普通文档
  > 模型常识
```

### 13.1 Skills 选择链路复用与扩展

权威入口继续使用 `backend/apps/chat/curd/custom_prompt.py::find_data_skills`，不新增并行路由服务。调用约定：

```text
用户请求（可选 data_skill_id）
  -> 构建权限快照
  -> BusinessSqlContextService.build
  -> find_data_skills
     -> 按 target_scope、平台/工作空间/个人作用域、用户启停过滤
     -> 校验当前数据源范围和 Skill 必需表
     -> 有 data_skill_id：使用用户指定 Skill，并沿用现有同类覆盖/去重
     -> 无 data_skill_id：沿用 embedding/关键词自动匹配、foundation Skill 和最多 12 条限制
  -> 将选中 Skill 与知识库上下文合并
  -> 固化 Skill ID、选择模式、权限版本和上下文 hash
```

`find_data_skills` 当前通过 `_dedupe_overridden_data_skills` 处理同名或近似 Skill 的覆盖关系，优先级及数据源限定规则继续以现有代码为准。知识库模块不得另行排序、恢复被去重 Skill 或根据知识命中结果改选 Skill。事件、Schema、表、字段和 JSON Path 权限属于额外交集约束，只能缩小可用上下文，不能扩大 Skill 可访问的数据范围。

### 13.2 统一调用链

```text
用户请求
  -> 确认用户、工作空间和当前数据源
  -> PermissionScopeService 构建元数据与数据权限快照
  -> BusinessSqlContextService 调用现有 find_data_skills（显式选择或自动匹配）
  -> 精确加载事件、JSON 映射和业务知识
  -> 文档 RAG 召回并按权限、适用性重排
  -> BusinessSemanticContextService 固定统一上下文快照
  -> 模型生成 SQL、分析计划或回答
  -> SQL AST 校验 Schema、表、字段和 JSON 表达式
  -> 应用事件规则、只读安全、行权限和脱敏规则
  -> 执行或返回结果
  -> 记录知识引用、Skill 选择、权限版本和告警
```

## 14. 四条调用链接入

### 14.1 Smart Q&A

修改：

- `backend/apps/chat/task/llm.py`
- `backend/apps/chat/task/smart_qa_graph.py`
- `backend/apps/chat/curd/agent_context_snapshot.py`
- `backend/apps/chat/models/chat_model.py`（只在现有 JSON 快照无法满足时调整）

流程：

```text
确定 datasource
  -> 构建用户事件/Schema/数据权限快照
  -> BusinessSqlContextService.build 调用现有 find_data_skills
  -> 复用用户指定或自动匹配的平台、工作空间和个人 Skills
  -> 统一结构化知识/RAG 检索一次
  -> 保存 agent_context_snapshot
  -> 生成/修复 SQL
  -> SQL AST、事件、Schema、字段、JSON Path 和数据权限后置校验
  -> 生成图表和回答
```

同一个 task 不重复检索。快照增加知识 version hash、citation IDs 和 warnings。

Smart Q&A 最终任务结果和会话记录接口返回安全引用摘要；前端 `frontend/src/views/chat/answer/ChartAnswer.vue` 在答案下方展示可折叠的“知识来源”，只展示名称、类型、章节和版本，不展示内部文件路径或其他工作空间信息。

### 14.2 AI 看板 SQL

修改：

- `backend/apps/dashboard/models/dashboard_model.py`
- `backend/apps/dashboard/crud/ai_sql_generator.py`
- `frontend/src/views/dashboard/common/DashboardSqlEditor.vue`

Graph 调整：

```text
collect_context
  -> normalize_manual_config
  -> build_permission_scope
  -> build_business_sql_context（内部调用现有 find_data_skills）
  -> retrieve_knowledge
  -> build_formula_ir
  -> deterministic_validate
  -> build_sql_plan
  -> generate_sql
  -> validate_sql
  -> finalize_response
```

检索放在配置标准化后，确保 query 使用实际指标、维度和筛选。`DashboardAiSqlGenerateResponse` 增加：

```python
knowledge_citations: list[dict[str, object]] = Field(default_factory=list)
knowledge_version_hash: str | None = None
retrieval_warnings: list[str] = Field(default_factory=list)
```

保存到看板时只保存引用和 hash，不复制知识正文。

AI SQL 生成结果区域展示本次采用的知识名称和 warning，用户可以据此判断 SQL 是否使用了预期口径。

### 14.3 综合分析助手

修改：

- `backend/apps/analysis_assistant/api/analysis_assistant.py`
- `backend/apps/chat/curd/agent_context_snapshot.py`
- `frontend/src/api/analysisAssistant.ts`
- `frontend/src/views/analysis-assistant/AnalysisAssistantDock.vue`

在规划前完成一次检索并固定快照，分析计划、时间策略、SQL 生成、SQL 修复、结果语义校验、分块总结和最终回答全部复用相同 `semantic_context`。

该快照同时固定权限版本、授权 Schema、事件范围、选中的平台/工作空间/个人 Skills 和知识版本；长任务过程中任一权限被撤销时，SQL 执行前必须重新确认授权，不能因为快照存在而继续执行已撤销访问。

SSE `context_snapshot` 增加 citations 和 warnings；前端可在结果详情展示引用，但不把内部 chunk ID 作为主要用户文案。

### 14.4 看板问答和报告解读

修改 `backend/apps/analysis_assistant/api/analysis_assistant.py`：

- 删除运行时对 `_collect_data_skill_context` 和 `_collect_tracking_context` 的使用。
- 不再 `include_all_target_scopes=True`；统一调用 `find_data_skills`，按当前场景、作用域和用户权限选择 Skills。
- 使用 `BusinessSemanticContextService`。
- 检索只使用问题、图表标题、字段和指标。
- 可见图表数据是事实来源，知识不重新计算图表结果。
- SSE 返回安全引用摘要，前端看板问答结果展示知识名称、章节和版本。

## 15. 管理 API

保留 `/knowledge-base` 前缀，调整为资源化接口：

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| GET | `/knowledge-base/list` | 分页、类型、作用域、状态和关键词筛选 |
| GET | `/knowledge-base/{id}` | 条目、草稿、发布版和管理权限 |
| POST | `/knowledge-base/draft` | 新建条目和草稿 |
| PUT | `/knowledge-base/{id}/draft` | 更新草稿 |
| POST | `/knowledge-base/{id}/validate` | 校验当前草稿 |
| POST | `/knowledge-base/{id}/publish` | 单条发布 |
| GET | `/knowledge-base/{id}/versions` | 历史版本 |
| GET | `/knowledge-base/{id}/versions/{version_id}` | 版本详情 |
| POST | `/knowledge-base/{id}/rollback` | 从历史版本创建新草稿 |
| PUT | `/knowledge-base/{id}/workspace-enabled` | 当前工作空间启停平台知识 |
| POST | `/knowledge-base/retrieval-preview` | 管理员调试召回 |
| DELETE | `/knowledge-base/{id}` | 未发布条目删除；已发布条目归档 |

接口返回统一错误结构：机器码、字段路径、错误类型、中文安全消息和可修复建议。HTTP 状态码和机器码只供程序判断，响应体和页面不得向用户显示 `409 Conflict`、`CONFLICT`、`KNOWLEDGE_*`、异常类名、堆栈或裸状态码。

### 15.1 用户可见错误提示规范

- 后端每个可预期业务错误必须同时返回稳定机器码和明确中文 `message`；不能只返回英文短语、数据库错误或第三方服务原文。
- 前端按机器码映射 `vue-i18n` 文案；简体中文环境必须显示中文。其他语言按当前语言包展示，映射缺失时回退到后端中文 `message`，不得回退到机器码。
- 字段校验错误应说明具体字段和修复方式；权限错误不得泄露其他工作空间、物理路径、文件 ID、Schema 或事件名称。
- 未知异常统一显示“操作失败，请稍后重试。”并附可追踪的请求 ID；完整技术信息只写服务端日志。
- Worker、文档解析、Embedding 和数据库异常必须在接口边界转换为安全中文提示，不能把第三方英文错误直接透传到页面。

第一阶段至少统一以下提示：

| 机器码 | 用户可见中文提示 |
| --- | --- |
| `KNOWLEDGE_DRAFT_CONFLICT` | 该知识已被其他用户更新，请刷新后重新编辑。 |
| `KNOWLEDGE_PUBLISHING` | 该知识正在发布中，请稍后再试。 |
| `KNOWLEDGE_VALIDATION_FAILED` | 知识校验未通过，请根据提示修改后重试。 |
| `KNOWLEDGE_PUBLISH_FAILED` | 知识发布失败，当前已发布版本不受影响，请稍后重试。 |
| `KNOWLEDGE_FILE_PARSE_FAILED` | 文档解析失败，请检查文件格式后重新上传。 |
| `KNOWLEDGE_FORBIDDEN` | 您没有权限执行此操作。 |
| `KNOWLEDGE_NOT_FOUND` | 该知识不存在或您无权查看。 |

## 16. 前端设计

### 16.1 页面结构

现有 `frontend/src/views/knowledge-base/index.vue` 拆分为：

```text
frontend/src/views/knowledge-base/
  index.vue
  components/
    KnowledgeToolbar.vue
    KnowledgeTable.vue
    KnowledgeDetailDrawer.vue
    KnowledgeEditorDrawer.vue
    KnowledgeValidationPanel.vue
    KnowledgeVersionDrawer.vue
    KnowledgeRetrievalPreview.vue
    editors/
      DocumentEditor.vue
      BusinessKnowledgeEditor.vue
      EventKnowledgeEditor.vue
      JsonFieldKnowledgeEditor.vue
frontend/src/components/knowledge/
  KnowledgeCitationList.vue
```

这是管理工具，主视图使用可筛选表格而不是卡片墙；详情和编辑使用抽屉，不嵌套卡片。

### 16.2 编辑能力

- DOCUMENT：Markdown textarea + `markdown-it` 预览，支持 Markdown/Word 上传，不新增编辑器依赖。
- BUSINESS：术语表单 + 可增删 SQL 示例；允许仅问题和 SQL。
- EVENT：事件基本信息 + 参数明细表。
- JSON_FIELD：Schema/表/宿主字段选择器 + JSON Path + 表达式。

Skills 继续在原 `frontend/src/views/data-skills/index.vue` 管理，并保留平台、工作空间、个人空间筛选和既有编辑能力；知识库页面不提供 Skill 编辑器，也不改变原页面逻辑。

表和字段选择复用 datasource metadata API。手工输入的物理对象在校验前不允许发布。

### 16.3 状态和操作

- 列表展示草稿、待发布、发布中、已发布、失败、停用和归档。
- 保存只保存草稿。
- 校验通过后显示发布按钮。
- 发布中轮询版本/任务状态。
- 编辑器保存时提交当前 `draft_version_id` 和 `revision`；收到并发冲突后保留本地编辑内容，展示后端中文提示并提供刷新操作，不自动重试覆盖。
- 版本抽屉显示变更摘要和回滚入口。
- 工作空间查看平台知识时显示“在本工作空间启用”开关和原因输入。

### 16.4 API 类型

扩展 `frontend/src/api/knowledgeBase.ts`，使用 discriminated union 定义四类 payload，避免页面以 `any` 传递结构化知识。

### 16.5 页面样式约束

- 以现有系统管理区页面为视觉基线，复用 Element Plus Secondary 组件和项目已有主题变量，不新增知识库专属设计系统。
- 主页面沿用系统管理区的页面标题、右侧工具栏和内容区结构；筛选输入、下拉框、主按钮和表格高度保持现有同类页面节奏。
- 列表使用紧凑表格，详情、编辑、校验和版本历史使用统一抽屉；不在抽屉内嵌套装饰卡片。
- 四类编辑器共享 `KnowledgeEditorDrawer` 的标题区、滚动内容区和固定底部操作区，操作顺序统一为取消、保存草稿、校验、发布。
- 状态标签复用平台语义色：处理中/待发布使用信息色，成功使用成功色，失败使用危险色，停用/归档使用中性色；不得按知识类型任意创造颜色。
- 按钮优先使用现有图标组件和图标按钮规范，未知图标提供 tooltip；删除、回滚和停用使用现有确认弹窗样式。
- 字号、字重、边框半径和间距复用现有 CSS 变量与组件默认值，卡片或抽屉内部容器圆角不超过现有 8px 规范。
- 页面默认浅色，遵守 `frontend/src/utils/theme.ts` 的 `COLOR_THEME_SWITCHING_ENABLED=false`，不增加新的主题入口或系统暗色跟随。
- 1366px、1440px 和 1920px 桌面宽度下验证工具栏、表格和抽屉；较窄宽度下筛选区换行且按钮、状态和长 stable key 不重叠。
- 所有文案通过 `vue-i18n`，同步维护简体中文、繁体中文、英文和韩文；不在组件中硬编码仅中文文案。

## 17. 配置和观测

新增后端配置：

```text
KNOWLEDGE_RETRIEVAL_ENABLED=true
KNOWLEDGE_RETRIEVAL_TOP_K=5
KNOWLEDGE_RETRIEVAL_MAX_CONTEXT_CHARS=12000
KNOWLEDGE_RETRIEVAL_MIN_SCORE=0.40
KNOWLEDGE_CHUNK_SIZE=1200
KNOWLEDGE_CHUNK_OVERLAP=150
KNOWLEDGE_PUBLISH_TIMEOUT_SECONDS=900
```

继续复用现有 Embedding 配置、本地 `local-*` Worker 队列以及 `find_data_skills` 当前匹配阈值和数量限制；不为 Skills 新增重复配置。

指标：

- 发布成功率、失败阶段和耗时。
- 文档解析、切片和 Embedding 耗时。
- 检索耗时、候选数、命中数和降级率。
- applicability valid/invalid/stale 数量。
- 各 surface 的知识命中率。
- 各作用域 Skill 候选数、选择数、显式/自动模式和选择耗时。
- 召回前元数据权限过滤数、生成后 SQL 权限拒绝数。

日志只记录 ID、hash、score、模型、耗时和错误类型，不记录完整知识正文、完整模型输出或凭据。

## 18. 数据迁移和兼容

### 18.1 现有知识库文档

- 每个现有 `knowledge_base` 行创建 DOCUMENT version 1。
- `READY` 且正文非空的记录迁移为当前发布版本并补建切片/向量。
- `PENDING/PROCESSING/FAILED` 迁移为草稿并保留错误信息。
- 源文件继续保留，不在迁移中删除。

### 18.2 现有 Data Skills

- 不迁移、不复制、不改变现有 `custom_prompt` 记录。
- 保留原 Skills 页面、API、存储、启停、用户私有范围和既有调用路径。
- 不新增 Skill 迁移、路由表或并行选择路径；统一上下文直接复用 `find_data_skills` 的现有结果。
- 上线前审计现有平台、工作空间和个人作用域字段是否完整；缺少明确作用域或所有者的记录继续按现有选择逻辑处理，并记录可定位告警。

### 18.3 现有 tracking 配置

- 第一阶段不强制把现有 tracking 配置拆成知识条目，也不修改原记录。
- 可选的只读索引任务可以为现有 tracking 生成检索镜像和 `knowledge_base_source_reference`，但现有 tracking 仍是权威来源。
- 其他表/字段注释继续保留在工作空间元数据，不强行转成知识类型。
- 索引脚本幂等，按 tenant、datasource、source type 和 source ID 识别已索引记录。

### 18.4 上线开关

建议增加：

```text
KNOWLEDGE_MANAGEMENT_V2_ENABLED=false
KNOWLEDGE_RUNTIME_CONTEXT_ENABLED=false
```

发布顺序：先迁移知识和双读校验，再打开 V2 知识管理入口，最后灰度统一知识上下文。Skills 始终使用当前选择路径；关闭知识运行开关时回到现有 tracking/语义路径，不删除新知识数据。

## 19. 文件改造范围

### 19.1 后端新增

```text
backend/apps/knowledge_base/schemas.py
backend/apps/knowledge_base/repository.py
backend/apps/knowledge_base/permissions.py
backend/apps/knowledge_base/validators.py
backend/apps/knowledge_base/normalizers.py
backend/apps/knowledge_base/chunking.py
backend/apps/knowledge_base/publisher.py
backend/apps/knowledge_base/source_references.py
backend/apps/knowledge_base/applicability.py
backend/apps/knowledge_base/retrieval.py
backend/apps/datasource/crud/permission_scope.py
backend/apps/datasource/crud/semantic_context.py
backend/apps/datasource/crud/metadata_permission.py
backend/alembic/versions/153_knowledge_base_rag_foundation.py
```

迁移编号以实际 Alembic head 为准，文件名中的 153 仅表示当前 152 之后的下一迁移顺序；实现时必须核对 revision/down_revision。

### 19.2 后端修改

```text
backend/apps/knowledge_base/models.py
backend/apps/knowledge_base/api/knowledge_base.py
backend/apps/knowledge_base/tasks.py
backend/common/core/task_registry.py
backend/common/core/config.py
backend/apps/chat/curd/custom_prompt.py
backend/apps/chat/curd/custom_prompt_manage.py
backend/apps/chat/curd/agent_context_snapshot.py
backend/apps/chat/task/llm.py
backend/apps/chat/task/smart_qa_graph.py
backend/apps/datasource/crud/sql_engine.py
backend/apps/datasource/crud/permission.py
backend/apps/datasource/crud/permission_rules.py
backend/apps/datasource/api/permission.py
backend/apps/system/crud/tracking_config.py
backend/apps/system/api/tracking_config.py
backend/apps/dashboard/models/dashboard_model.py
backend/apps/dashboard/crud/ai_sql_generator.py
backend/apps/analysis_assistant/api/analysis_assistant.py
```

### 19.3 前端新增/修改

```text
frontend/src/views/knowledge-base/index.vue
frontend/src/views/knowledge-base/components/**
frontend/src/components/knowledge/KnowledgeCitationList.vue
frontend/src/api/knowledgeBase.ts
frontend/src/api/chat.ts
frontend/src/api/dashboard.ts
frontend/src/views/system/data-dictionary/DataDictionary.vue
frontend/src/views/dashboard/common/DashboardSqlEditor.vue
frontend/src/views/chat/answer/ChartAnswer.vue
frontend/src/views/analysis-assistant/AnalysisAssistantDock.vue
frontend/src/api/analysisAssistant.ts
frontend/src/i18n/zh-CN.json
frontend/src/i18n/zh-TW.json
frontend/src/i18n/en.json
frontend/src/i18n/ko-KR.json
```

### 19.4 代码组织与模块拆分

- 不创建同时承载模型、CRUD、校验、发布、检索和权限的大文件；按本节既定模块边界实现。
- 后端按模型与 Schema、仓储、校验、发布、切片、检索、适用性和权限等职责拆分，公共流程通过明确接口组合。
- `knowledge-base/index.vue` 只负责页面编排和状态协调，四类编辑器、版本记录、校验结果和引用列表分别放入独立组件。
- 现有大文件只做必要接入；新增复杂逻辑下沉到独立服务或组件，不借本需求进行无关重构。
- 是否拆分以职责是否独立、接口是否清晰、能否独立测试为判断标准，不设置机械行数限制，也不创建没有独立语义的碎片文件。

## 20. 测试设计

### 20.1 新增后端测试

```text
backend/tests/test_knowledge_base_models.py
backend/tests/test_knowledge_base_payload_validation.py
backend/tests/test_knowledge_base_version_lifecycle.py
backend/tests/test_knowledge_base_permissions.py
backend/tests/test_knowledge_base_workspace_override.py
backend/tests/test_knowledge_base_applicability.py
backend/tests/test_knowledge_base_publish.py
backend/tests/test_knowledge_base_chunking.py
backend/tests/test_knowledge_base_retrieval.py
backend/tests/test_knowledge_base_source_references.py
backend/tests/test_permission_scope_service.py
backend/tests/test_data_skill_context_integration.py
backend/tests/test_metadata_permission_service.py
backend/tests/test_business_semantic_context.py
backend/tests/test_knowledge_smart_qa_context.py
backend/tests/test_knowledge_dashboard_ai_sql.py
backend/tests/test_knowledge_analysis_assistant.py
backend/tests/test_knowledge_report_interpretation.py
backend/tests/test_knowledge_base_migration.py
```

### 20.2 必测场景

- 草稿保存不影响当前发布版本。
- 两个用户基于同一 revision 并发保存时只有一个成功，失败方收到中文并发提示且已保存内容不被覆盖。
- 同一条目并发上传文件发生冲突时，请求临时文件被清理，已保存版本的源文件不被删除或替换。
- 同一条目重复发布返回已有任务；多后端或多 Worker 同时发布时只有一个任务可以原子切换当前版本。
- 发布期间保存、校验、删除、归档和回滚均被阻止，并返回“该知识正在发布中，请稍后再试。”。
- 延迟 Worker 携带旧 revision 或 content hash 回写时不能切换 `current_version_id`。
- 校验失败不能发布。
- 发布外部 Embedding 失败时旧版本继续可用。
- 工作空间不能编辑或覆盖平台知识。
- 工作空间停用平台知识后，结构化加载和 RAG 都排除它。
- 同一平台映射在工作空间 A/B 分别校验各自数据源。
- 缺表、缺字段或 JSON Path 失效时不做替代。
- SQL 示例通过只读、事件、Schema、表、字段、JSON Path 和数据权限校验。
- 无事件权限时对应事件知识、事件属性和引用它们的 Skills 均不进入 Prompt。
- Schema、事件和事件属性权限继续使用现有 `ds_rules` 用户/白名单绑定，平台和工作空间规则隔离正确。
- 未配置独立事件权限时正确继承表、字段和 JSON Path 权限；配置后按禁止规则缩小范围。
- 无 Schema、表或字段权限时不召回相关知识或 Skills，也不在引用摘要中泄露对象名称。
- 个人空间 Skill 仅创建者进入候选；其他用户和其他工作空间无法读取或调用。
- 有 `data_skill_id` 时使用用户明确选择；没有时按现有逻辑自动匹配平台、工作空间和个人 Skills。
- 同名或近似 Skills 沿用 `_dedupe_overridden_data_skills` 的覆盖/去重结果，知识库接入不改变其优先级。
- 生成后 SQL AST 引用无权对象时阻断执行；行级权限和脱敏规则继续生效。
- 向量模型或维度变化后旧 chunk 不参与检索并进入重建流程。
- 四条调用链保存权限、Skill 选择和知识版本快照。
- 报告解读不再静默吞掉语义上下文错误。
- 只读索引重复执行不生成重复知识镜像或来源引用。
- `find_data_skills` 的显式选择、自动匹配、作用域过滤、foundation Skill 和最多 12 条行为无回归。

### 20.3 前端测试

- 四类 payload 的表单序列化。
- 业务知识允许只有问题和 SQL。
- 草稿、校验、发布按钮状态。
- 发布轮询和失败状态。
- 平台/工作空间权限和平台停用开关。
- 版本查看与回滚确认。
- 所有业务错误在简体中文环境显示明确中文提示；机器码、HTTP 英文短语、异常类名和第三方英文错误不得直接出现在页面。
- 未配置前端错误码映射时回退到后端中文安全消息；未知错误显示统一中文提示和请求 ID。
- 原 Skills 页面、编辑、启停和个人空间能力保持不变。
- Smart Q&A、AI 看板和综合分析助手只展示安全引用字段，不暴露内部路径和跨工作空间信息。
- 知识库主页面、四类编辑器、校验面板和版本抽屉在 1366px、1440px、1920px 下无重叠、溢出和异常位移。
- 新增控件复用现有主题变量，浅色主题下状态色、禁用态、错误态和 focus 态与系统管理区一致。

### 20.4 回归命令

```powershell
backend\.venv\Scripts\python.exe -m pytest backend/tests/test_knowledge_base_*.py -q
backend\.venv\Scripts\python.exe -m pytest backend/tests/test_permission_scope_service.py backend/tests/test_metadata_permission_service.py backend/tests/test_data_skill_context_integration.py backend/tests/test_data_skill_sql_validation.py backend/tests/test_tracking_excel.py backend/tests/test_dashboard_ai_sql_generator.py backend/tests/test_analysis_assistant_sql_generation.py -q
Set-Location frontend
npm run build
```

## 21. 实施阶段

### 阶段一：主数据和版本发布基础

- 数据库迁移、四类 payload、草稿、校验、单条发布、版本和回滚。
- 保持运行上下文开关关闭。
- 验收：管理 API 生命周期完整，旧线上路径不受影响。

### 阶段二：结构化知识和运行适配

- 现有 tracking 与知识库 EVENT/JSON 的只读组合和来源去重。
- 平台结构化知识 applicability。
- 验收：原 tracking 页面/API/存储不变，统一 AI 上下文可读取无重复且无冲突的组合结果。

### 阶段三：切片和 RAG

- 文档解析、标准化、chunk、pgvector、检索、引用和审计。
- 工作空间停用进入检索过滤。
- 验收：retrieval preview 能证明租户隔离、版本过滤和适用性过滤。

### 阶段四：权限快照、Skills 选择复用和统一上下文

- `PermissionScopeService` 和召回前权限过滤。
- Catalog/Schema 与事件/事件属性权限扩展及继承策略。
- 复用 `find_data_skills`，覆盖显式选择与自动匹配，并补充权限交集和选择审计。
- `BusinessSemanticContextService`。
- Smart Q&A 和 AI 看板 SQL 接入。
- SQL AST 和数据权限后置校验。
- 验收：SQL 生成使用同一权限、Skill 与知识快照，引用可追踪；`data_skill_id` 及未指定时的自动匹配行为与当前项目一致。

### 阶段五：分析与看板问答

- 综合分析助手和报告解读接入。
- 删除报告解读旁路加载。
- 验收：计划、SQL 修复、总结和报告解读遵守同一知识边界。

### 阶段六：前端统一入口和迁移上线

- 四类编辑器、版本、发布、停用、引用预览。
- 迁移现有知识库文档；现有 Skills 和 tracking 不做破坏性迁移。
- 保持旧 Skills 和数据字典页面逻辑，独立开关灰度和全量回归。

## 22. 风险和控制

### 22.1 新旧配置重复生效

控制：事件/JSON 来源引用和 stable key 冲突检测；Skills 只复用现有 `find_data_skills` 结果，不复制主数据或重复匹配。

### 22.2 发布中途失败

控制：Embedding 在事务外准备，最终切换短事务完成；旧版本不提前删除。

### 22.3 平台知识误用于不兼容数据源

控制：当前工作空间 Schema hash + applicability；invalid 条目同时排除结构化上下文和 RAG。

### 22.4 Prompt 注入和敏感日志

控制：低优先级标签、系统规则声明、日志只存 ID/hash/score，不记录完整正文。

### 22.5 上下文过长

控制：结构化上下文、Top-K、得分阈值、分类型字符预算和单请求固定快照。

### 22.6 回滚困难

控制：功能开关、非破坏迁移、旧字段兼容保留、运行上下文可独立关闭。

### 22.7 同一知识条目并发覆盖

控制：草稿 revision 乐观锁、独立上传临时文件、租户级发布锁、数据库发布状态条件更新和幂等任务。所有用户可见冲突均返回中文业务提示，不允许后写覆盖、过期 Worker 回写或前端静默重试。

## 23. 完成定义

开发完成必须同时满足：

1. 四类知识均能在统一页面逐条结构化编辑，Skills 保留独立页面和既有逻辑。
2. 平台和工作空间知识均支持草稿、校验、单条发布、版本和回滚。
3. 工作空间停用平台知识同时影响结构化加载和 RAG。
4. 平台物理知识按使用方工作空间数据源动态校验。
5. 发布失败不影响上一版本。
6. Smart Q&A、AI 看板 SQL、AI 看板问答/报告解读和综合分析助手使用统一语义/RAG 服务。
7. SQL 始终通过事件、Schema、表、字段、JSON Path、只读、行权限、脱敏和选中 Skills 校验。
8. 所有知识使用均可追踪到知识、版本和切片。
9. 平台、工作空间和个人空间 Skills 沿用当前项目逻辑：支持 `data_skill_id` 显式选择，未指定时自动匹配，且不能扩大用户权限。
10. 现有 Skills 页面、API、存储、启停、场景范围、覆盖去重和既有调用逻辑保持不变。
11. 召回前不会向模型暴露无权事件或 Schema 元数据，生成后无权 SQL 会被阻断。
12. 同一知识条目的并发保存、上传、发布、删除和回滚不会互相覆盖，冲突返回明确中文提示。
13. 简体中文环境下所有用户可见错误均转换为安全、明确的中文业务提示；其他语言使用对应语言包，任何环境都不展示机器码、英文异常原文或内部技术信息。
14. 新增测试、关键既有回归和前端构建全部通过。
