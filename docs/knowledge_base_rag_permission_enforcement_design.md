# 知识库与 Skills 权限对象及执行约束设计

## 1. 文档定位

本文是 `knowledge_base_rag_development_design.md` 的权限专项配套设计，补齐以下实现约束：

- 知识和 Skills 的对象引用索引。
- Catalog/Schema/表/字段/JSON Path 的规范标识与 SQL AST 校验。
- 事件和事件属性权限的执行语义。
- `permission_version` 的可靠生成与缓存失效。
- Schema、事件和事件属性权限的管理页面。

发生冲突时，本文对权限对象建模和执行约束的描述优先于主开发文档中的概述。

## 2. 权威边界

1. 当前工作空间通过 `get_bound_datasource_id_for_tenant` 取得唯一活动数据源；不得信任客户端传入的 tenant、数据源归属或旧 `CoreDatasource.tenant_id` 推断。
2. 数据源访问、Schema、表、字段、JSON Path、事件、事件属性、行权限和脱敏规则取交集，任一层拒绝即拒绝。
3. `custom_prompt` 继续是 Skills 唯一主数据；对象引用索引只是可重建的安全投影，不改变 Skill 管理和选择语义。
4. `sys_tenant_tracking_*` 继续是现有事件字典的权威来源；知识库 EVENT/JSON_FIELD 与其只读组合。
5. 对象引用无法确定、权限版本无法确定或 SQL 无法证明安全时失败关闭，不使用相似名称或默认对象替代。

## 3. 规范对象标识

发布时使用不携带数据源上下文的声明值对象：

```python
@dataclass(frozen=True)
class DeclaredObjectPath:
    object_type: Literal[
        "SCHEMA", "TABLE", "FIELD", "JSON_PATH", "EVENT", "EVENT_PROPERTY"
    ]
    catalog: str | None = None
    schema: str | None = None
    table: str | None = None
    field: str | None = None
    json_path: str | None = None
    event_name: str | None = None
    event_property_key: str | None = None
```

`DeclaredObjectPath` 只表示作者声明的物理/业务路径，不包含 `tenant_id` 或 `datasource_id`。进入使用方上下文后解析为不可变值对象 `SemanticObjectKey`：

```python
@dataclass(frozen=True)
class SemanticObjectKey:
    object_type: Literal[
        "SCHEMA", "TABLE", "FIELD", "JSON_PATH", "EVENT", "EVENT_PROPERTY"
    ]
    tenant_id: int
    datasource_id: int
    catalog: str | None = None
    schema: str | None = None
    table: str | None = None
    field: str | None = None
    json_path: str | None = None
    event_name: str | None = None
    event_property_key: str | None = None
```

`SemanticObjectKey` 表示已经针对当前工作空间和数据源解析完成的对象，因此 `tenant_id` 和 `datasource_id` 必填。平台知识和未固定数据源的平台 Skill 在发布时只保存 `DeclaredObjectPath`；进入某个工作空间时再解析成 `SemanticObjectKey`，不能把平台声明绑定到发布管理员当时所在的数据源。

### 3.1 物理对象目录的权威模型

第一期扩展现有 `CoreTable/CoreField`，不新增与其平行且需要双写的第二套物理对象目录：

- `CoreTable` 增加原始展示值 `catalog_name/schema_name`，以及非空的方言归一键 `catalog_key/schema_key/table_key`。不支持 Catalog 或 Schema 的方言使用明确的空归一键，不能用数据库名、首个 Schema 或当前登录用户静默代替。
- 表唯一约束改为 `(ds_id, catalog_key, schema_key, table_key)`；`CoreField` 继续通过 `table_id` 继承完整表键，增加方言归一的非空 `field_key`，并使用 `(table_id, field_key)` 唯一约束，原始 `field_name` 只用于展示。
- 连接器的 Schema 刷新结果必须携带可获得的 Catalog/Schema/表原始值。迁移时可从数据源 `dbSchema` 或方言唯一默认 Schema 确定性回填；无法确定且数据源存在多个 Schema 时标记目录不完整，相关知识、Skill 和 SQL 失败关闭。
- 当前按 `(ds_id, table_name)` 查询和按裸 `table_name` 构建字典的调用方必须迁移为完整键。兼容适配器只有在当前数据源中恰好存在一个匹配表时才能解析裸表名；零个或多个匹配都返回明确缺失/歧义结果，不能选择第一条。
- `physical_schema_hash` 基于排序后的完整表键、字段键和必要类型信息生成；刷新事务完成目录 upsert/delete 后在同一事务递增 SCHEMA epoch。
- `CoreTable.custom_comment/CoreField.custom_comment` 等工作空间业务元数据仍遵守工作空间边界。完整物理键只解决对象身份，不把工作空间注释写回业务数据库或提升为平台公共元数据。

规范化规则：

- 标识符按当前数据库方言执行去引号和大小写归一，保留原始显示值用于页面展示。
- TABLE 键必须包含解析后的 Catalog/Schema/表；单 Schema 数据源中的非限定表名在解析阶段补成当前有效 Schema。
- 多 Schema 数据源中的非限定表名视为歧义并阻止发布或执行，不回退到第一个 Schema。
- FIELD 继承完整 TABLE 键；JSON_PATH 继承完整 FIELD 键。
- EVENT 使用 `tenant_id + datasource_id + event_name` 作为业务唯一范围，并关联事件物理表和事件名字段。
- EVENT_PROPERTY 使用事件名和属性稳定键，并关联来源字段或 JSON Path。
- `canonical_key` 使用稳定 JSON 序列化后计算 SHA-256；不通过字符串拼接临时构造权限键。

## 4. 对象引用投影

### 4.1 `semantic_object_reference`

新增通用派生索引表：

| 字段 | 说明 |
| --- | --- |
| `id` | 主键 |
| `tenant_id` | 所属租户边界 |
| `owner_type` | KNOWLEDGE_VERSION/KNOWLEDGE_CHUNK/DATA_SKILL |
| `owner_id` | version、chunk 或 custom_prompt ID |
| `knowledge_base_id/version_id/chunk_id/skill_id` | 可查询的显式归属列 |
| `object_type` | SCHEMA/TABLE/FIELD/JSON_PATH/EVENT/EVENT_PROPERTY |
| `datasource_id` | 工作空间知识或数据源限定 Skill 的数据源；平台声明可空 |
| `catalog/schema_name/table_name/field_name` | 物理对象原始值 |
| `json_path/event_name/event_property_key` | 业务对象原始值 |
| `declared_key` | 不含使用方 datasource ID 的规范声明哈希 |
| `resolution_status` | RESOLVED/UNRESOLVED/AMBIGUOUS/STALE |
| `source_kind` | EXPLICIT/SQL_AST/STRUCTURED_PAYLOAD/SKILL_RULE/INHERITED |
| `create_time` | 创建时间 |

约束：

- 唯一键为 `(owner_type, owner_id, declared_key, source_kind)`。
- `owner_type` 与对应归属 ID 使用 CHECK 保证只有一个有效所有者。
- 知识版本发布后引用投影不可变；新版本生成新投影。
- chunk 使用 chunk 级引用；没有局部引用的 chunk 继承版本级引用。
- `UNRESOLVED`、`AMBIGUOUS` 或 `STALE` 引用不得进入线上上下文。

### 4.2 `semantic_object_resolution`

平台知识和平台 Skill 需要按使用方数据源动态解析，新增解析结果表：

| 字段 | 说明 |
| --- | --- |
| `reference_id` | 声明引用 ID |
| `tenant_id/datasource_id` | 使用方上下文 |
| `physical_schema_hash` | 解析时物理 Schema 指纹 |
| `canonical_key` | 解析后的 `SemanticObjectKey` 哈希 |
| `status` | RESOLVED/UNRESOLVED/AMBIGUOUS/STALE |
| `report` | 缺失、歧义和方言错误的安全摘要 |
| `checked_at` | 校验时间 |

`reference_id` 使用到 `semantic_object_reference.id` 的外键并级联删除派生解析结果。唯一键为 `(reference_id, tenant_id, datasource_id, physical_schema_hash)`；`status=RESOLVED` 时 `canonical_key` 必填，其他状态时为空。工作空间知识和固定数据源 Skill 在发布或索引时也可以写同一解析表，从而让召回查询始终使用一种解析结果模型。

解析流程必须遵循以下约束：

1. 平台知识和平台 Skill 发布时只固化 `DeclaredObjectPath`，不得写入发布管理员当前工作空间的数据源 ID。
2. 首次进入某个 tenant/datasource，或 `physical_schema_hash` 变化时，使用当前数据源方言和授权前物理目录重新解析全部声明。
3. 只有每个声明都得到当前 schema hash 下的 `RESOLVED` 记录时，owner 才能进入后续用户权限过滤；缺少解析记录不能视为可用。
4. 解析结果只证明物理适用性，不包含用户授权结论。用户权限仍通过本次请求的 `PermissionScopeSnapshot` 求交集。
5. Schema 刷新后旧 hash 的解析记录保留用于审计，但不参与当前请求；异步重建未完成时请求内必须同步解析或失败关闭，不能沿用旧结果。

### 4.3 各类型引用生成

- DOCUMENT：Payload 增加 `object_references`。上传文档中的 SQL 代码块使用 sqlglot 提取对象；工作空间文档正文命中当前对象目录中的物理标识但未声明时校验失败。平台文档不得读取发布管理员所在工作空间的对象目录，涉及物理对象时必须由作者显式声明，并在使用方动态解析。声明为数据源无关的文档不得包含 SQL 代码块、显式对象声明或确定性物理标识。
- BUSINESS：`related_objects` 生成显式引用；每条 SQL 示例通过 AST 生成 Schema、表、字段和 JSON Path 引用，两者必须一致。
- EVENT：根据事件表、事件名字段、时间字段、参数来源和事件名生成引用。
- JSON_FIELD：根据 Schema、表、宿主字段、JSON Path 和 expression AST 生成引用。
- DATA_SKILL：从现有结构化规则、`required_tables` 标记和 SQL 片段生成派生引用。无法解析必需对象的 Skill 保留在原管理页面，但不进入统一 AI 上下文，并记录可定位告警。

发布校验必须比较显式引用与解析引用。SQL 实际引用多于显式声明时阻止发布；显式声明未被使用可以作为警告，但不能自动删除。

### 4.4 `data_skill_object_projection`

Skill 没有知识库发布状态，且“合法地不引用物理对象”和“尚未完成扫描”都可能表现为零条引用。新增独立派生状态表：

| 字段 | 说明 |
| --- | --- |
| `skill_id` | `custom_prompt.id`，唯一 |
| `tenant_id/user_id/target_scope` | 冗余安全边界 |
| `source_hash` | 影响对象引用的 Skill 字段稳定哈希 |
| `projector_version` | 解析器/投影算法版本 |
| `status` | PENDING/READY/FAILED/STALE |
| `reference_count` | 已生成引用数，可为 0 |
| `error_code/checked_at` | 安全错误和检查时间 |

`custom_prompt` 仍是唯一主数据。Skill 新增或修改成功后创建 PENDING 投影并重建引用；删除时级联删除派生状态和引用。现有 Skills 通过幂等注册任务 `data_skill.rebuild_object_projections` 按主键游标补建。只有状态 READY、`source_hash` 与当前 Skill 内容一致且 `projector_version` 为当前版本时，零引用才表示已确认不依赖物理对象；其他状态均失败关闭。

## 5. 召回前权限过滤

`PermissionScopeSnapshot` 保存规范对象集合：

```python
@dataclass(frozen=True)
class PermissionScopeSnapshot:
    tenant_id: int
    user_id: int
    datasource_id: int
    permission_version: str
    schema_hash: str
    allowed_object_keys: frozenset[str]
    denied_object_keys: frozenset[str]
    row_constraints_hash: str
```

查询规则：

1. 候选知识版本必须是 `current_version_id`。Skill 在进入 `find_data_skills` 匹配和正文组装前，先按 READY 且 source hash 匹配的 `data_skill_object_projection` 和对象权限计算 `eligible_skill_ids`；显式 `data_skill_id` 不在集合中时返回权限/适用性错误，不回退自动匹配。
2. 对当前 tenant/datasource/schema hash 加载 `semantic_object_resolution`；任一声明没有 RESOLVED 结果时排除其 owner。
3. 对每个 version、chunk 或 Skill 使用 `NOT EXISTS` 排除任何 resolved canonical key 不在 `allowed_object_keys` 中或位于 `denied_object_keys` 中的引用。
4. 一项内容引用多个对象时必须全部允许，不能只要命中一个允许对象就召回。
5. 平台知识先完成当前 tenant/datasource 的 applicability 和对象解析，再执行当前用户权限过滤。
6. 过滤发生在数据库查询或投影查询层；被拒绝对象的名称、路径、示例值和切片正文不进入应用层 Prompt 组装。
7. 无对象引用的普通业务说明可以参与 RAG，但不得包含可执行 SQL 或确定性物理映射。

## 6. SQL 生成后强制校验

### 6.1 Schema 与物理对象

- 修改 `sql_permission.py`，从 sqlglot `exp.Table` 同时提取 catalog、db 和 table，解析成完整 TABLE 键。
- 修改 `sql_engine_executor.py`，`allowed_tables` 替换为规范对象集合；保留展示名仅用于中文错误消息。
- 字段校验必须绑定完整 TABLE 键，禁止跨 Schema 同名表共享字段权限。
- `SELECT *` 继续按当前严格规则处理；无法枚举授权字段时阻断。
- JSON 表达式提取宿主字段和静态 JSON Path；动态 Path 在存在路径限制时阻断。

### 6.2 事件权限

事件权限采用禁止型语义并编译为执行约束：

1. 没有独立事件权限记录时，事件继承事件表、事件名字段、参数字段和 JSON Path 权限。
2. 存在禁止事件时，权限服务根据 tracking 中的事件表和事件名字段生成 `event_name NOT IN (...)` 行约束，复用现有行权限 AST 注入和关系验证能力。
3. SQL 已包含事件谓词时，验证其取值集合不包含禁止事件；谓词为动态参数、子查询或无法求值表达式时，不以该谓词证明权限安全。
4. SQL 未限定事件且可以安全注入禁止条件时执行注入；存在 outer join、聚合层级或方言结构导致无法保持语义时直接阻断。
5. 事件属性权限同时要求事件允许、来源字段允许和 JSON Path 允许。
6. 事件专属属性只有在 SQL 谓词能够证明限定到允许事件时才能访问；否则阻断，不使用 CASE、NULL 或相似属性静默替代。
7. 权限改写后再次运行 Schema、表、字段、JSON Path、只读和行权限 AST 校验。

## 7. 权限版本与缓存失效

现有 `ds_rules`、`ds_permission` 和 `sys_tenant_user` 缺少统一可靠的更新时间，因此不直接使用 `MAX(update_time)` 作为权限版本。

新增 `semantic_scope_epoch`：

| 字段 | 说明 |
| --- | --- |
| `scope_type` | PERMISSION/SYSTEM_ROLE/MEMBERSHIP/DATASOURCE_ACCESS/DATASOURCE_ROLE/TRACKING/DATASOURCE_BINDING/SCHEMA |
| `tenant_id` | 工作空间 |
| `datasource_id` | 可空，数据源范围 |
| `subject_id` | 可空，用户或其他主体 |
| `epoch` | bigint，事务内单调递增 |
| `update_time` | 更新时间 |

所有相关写路径必须在同一数据库事务中执行 upsert `epoch = epoch + 1`：

- `ds_rules`、`ds_permission` 的新增、修改、删除、启停和用户/白名单变化。
- `UserModel.system_role`、用户启停状态变化使用 SYSTEM_ROLE；工作空间成员新增、删除、角色或状态变化使用 MEMBERSHIP。
- `CoreDatasourceUser` 新增、删除使用 DATASOURCE_ACCESS，项目角色变化使用 DATASOURCE_ROLE；系统用户接口、工作空间接口和数据源权限接口中的直接写路径必须调用同一 epoch 服务。
- tracking 配置、事件分组、Schema 元数据变化。
- 工作空间数据源绑定和解绑。
- `CoreTable/CoreField` 的新增、删除、启停、重命名、字段类型变化和数据源物理元数据刷新使用 SCHEMA；批量刷新可以在同一事务内合并为一次递增。

第一期提供唯一的 `bump_semantic_scope_epoch(...)` 写服务；现有直接 ORM/SQL 修改上述权威表的路径必须改为领域服务或在原事务内显式调用该服务。管理脚本、数据迁移和批量刷新也不能绕过。测试要覆盖每个公开写入口，而不是只测试 epoch helper 本身。

`permission_version` 为以下内容的稳定哈希：tenant/user/datasource、上述全部相关 epoch、当前系统角色与用户状态、工作空间成员角色与状态、`CoreDatasourceUser` 访问和项目角色、绑定 datasource ID、授权后 schema hash。缓存键必须包含该版本；版本变化后旧键自然失效，不依赖跨进程本地缓存删除。

权限快照构建不得先命中旧权限缓存再计算版本。`PermissionScopeRepository` 使用独立数据库连接开启只读 `REPEATABLE READ` 事务，不修改全局 SQLAlchemy engine 隔离级别；在同一快照内直接读取相关 `semantic_scope_epoch`、系统角色和状态、工作空间成员、数据源访问/项目角色、当前数据源绑定和 Schema 元数据版本，先计算 `permission_version`，然后才能使用包含该版本的权限内容缓存。不得假设默认 `READ COMMITTED` 下的多个查询属于同一一致性快照。

权限快照只在当前请求/任务内复用。模型生成可能持续较长时间，实际执行 SQL 前必须通过一个短一致性查询重新读取组成 `permission_version` 的 epoch 和权威状态；版本未变化才能执行，发生变化时丢弃旧执行权限并重新构建快照、重新做 AST 校验，无法安全重建时返回中文权限已变化提示。读取期间权威状态缺失或无法建立一致快照时失败关闭并重试一次；仍失败则不复用旧版本权限。

## 8. 权限管理页面

在现有权限管理页面扩展，不新建第二套授权页面：

- `frontend/src/api/permissions.ts` 增加 `schema`、`event`、`event_property` 类型和 DTO。
- `frontend/src/views/system/permission/index.vue` 增加 Schema、事件、事件属性三个权限类型入口。
- Schema 权限使用 Catalog/Schema 选择器；数据源只有一个有效 Schema 时显示继承状态，不创建冗余记录。
- 事件权限使用当前工作空间 tracking event catalog；事件属性选择器随事件联动，只展示其稳定属性键和来源摘要。
- 页面只提交稳定 ID/键，服务端重新解析当前 tenant、datasource 和对象归属。
- 用户可见冲突和权限错误显示中文安全消息，不展示其他工作空间对象名称。

## 9. 文件改造范围

新增：

```text
backend/apps/datasource/crud/semantic_object_key.py
backend/apps/datasource/crud/metadata_permission.py
backend/apps/datasource/crud/permission_scope.py
backend/apps/datasource/crud/permission_scope_repository.py
backend/apps/knowledge_base/object_references.py
backend/apps/knowledge_base/object_resolution.py
backend/apps/chat/curd/skill_object_references.py
backend/apps/chat/task/data_skill_object_projection.py
backend/alembic/versions/154_knowledge_base_retrieval_projection.py
backend/alembic/versions/155_semantic_permission_epoch.py
backend/tests/test_semantic_object_key.py
backend/tests/test_semantic_object_reference.py
backend/tests/test_semantic_object_resolution.py
backend/tests/test_data_skill_object_projection.py
backend/tests/test_event_permission_enforcement.py
```

修改：

```text
backend/apps/datasource/crud/sql_permission.py
backend/apps/datasource/crud/sql_engine_executor.py
backend/apps/datasource/crud/permission.py
backend/apps/datasource/crud/permission_rules.py
backend/apps/datasource/api/permission.py
backend/apps/datasource/models/datasource.py
backend/apps/datasource/crud/datasource.py
backend/apps/datasource/crud/table.py
backend/apps/chat/curd/custom_prompt.py
backend/apps/chat/curd/custom_prompt_manage.py
backend/apps/system/crud/tracking_config.py
backend/apps/system/crud/tenant.py
backend/apps/system/api/tenant.py
backend/apps/system/api/user.py
backend/apps/datasource/crud/binding.py
frontend/src/api/permissions.ts
frontend/src/views/system/permission/index.vue
frontend/src/i18n/zh-CN.json
frontend/src/i18n/zh-TW.json
frontend/src/i18n/en.json
frontend/src/i18n/ko-KR.json
```

## 10. 必测场景

- 两个 Schema 存在同名表时，授权其中一个不能访问另一个。
- 非限定表名在多 Schema 数据源中失败关闭。
- Schema 刷新后 `CoreTable/CoreField` 能持久化完整物理键；无法确定 Schema 的旧记录不会被当作默认 Schema 放行。
- 知识 chunk 或 Skill 引用任一无权对象时整体不进入 Prompt。
- 现有 Skill 投影未生成、失败、版本过旧或 source hash 不匹配时不进入匹配；READY 且零引用的 Skill 可以按原逻辑选择。
- 普通文档包含未声明 SQL 对象时不能发布。
- 禁止事件 SQL 被安全注入排除条件；无法安全注入时被阻断。
- 事件专属属性在没有可证明事件谓词时被阻断。
- 动态 JSON Path 在存在路径限制时被阻断。
- 平台声明在工作空间 A/B 分别解析为各自的数据源对象，不携带发布管理员的数据源；Schema hash 变化后旧解析结果不能继续使用。
- 权限规则、系统角色、用户状态、成员关系、数据源访问、项目角色、tracking、绑定或 Schema 任一公开写入口都会在同一事务改变对应 epoch 和 `permission_version`。
- `permission_version` 计算不读取旧权限缓存，并与角色、成员、数据源访问/角色、绑定、epoch 和 Schema 的只读 `REPEATABLE READ` 快照对应。
- 权限快照生成后发生撤权或 Schema 变化时，SQL 执行前版本复核能够阻止继续使用旧快照。
- 多后端实例使用同一权限版本，不依赖进程内缓存同步。
- 管理员可以在原权限页面配置 Schema、事件和事件属性权限。
