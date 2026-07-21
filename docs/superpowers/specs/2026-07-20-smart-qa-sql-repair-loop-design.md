# Smart Q&A SQL 受控修复闭环设计

## 背景

2026 年 7 月 20 日通过真实 AI 看板页面串行执行 100 个问题，确认存在 5 个真实 AI/SQL 失败：

- `q025` 生成递归 CTE 后在数据库执行阶段失败，错误为 `missing column aliases in recursive WITH query`。
- `q043` 生成非法 `CAST(..., AS DECIMAL(...))`，在 SQL 准备阶段解析失败。
- `q045`、`q048`、`q086` 首次生成和现有一次语义重写均未遵守 `ServerPayLog + personal.money + COUNT(DISTINCT uid)` 的 Data Skills 口径，最终被语义校验器正确拒绝。

完整测试证据位于：

- `.codex-runtime/ai-dashboard-100-test/ui-final-report.md`
- `.codex-runtime/ai-dashboard-100-test/ui-summary.json`

当前 Smart Q&A 工作流为线性流程：

```text
generate_sql -> prepare_sql -> execute_sql -> generate_chart
```

`prepare_sql` 只针对 `DataSkillSqlValidationError` 提供一次专用重写；普通 SQL 解析错误直接终止。`execute_sql` 遇到非权限、非数据不可用异常时直接抛出，数据库返回的可修复语法或方言错误没有恢复路径。Data Skills 校验器命中规则后只返回展示消息，修复请求拿不到必需字段、禁止字段和正则规则等结构化证据。

## 目标

- 为 SQL 解析错误、Data Skills 语义错误和数据库可恢复语法/方言错误建立统一、有次数限制、可观测的修复闭环。
- 修复后的 SQL 必须重新经过 JSON 解析、Data Skills 校验、只读校验、表字段范围校验、用户权限校验和数据库执行，不允许直接绕过任何门禁。
- 核心修复能力保持业务领域无关；修仙收入、日期补齐等具体口径仅存在于 datasource 6 的 Data Skills、推荐看板 SQL 和测试夹具中。
- 修复失败时返回明确错误，不隐藏问题，不使用错误字段或近似字段静默替代。

## 非目标

- 不通过放宽、关闭或绕过 Data Skills 校验提高成功率。
- 不在共享后端代码中硬编码 `ServerPayLog`、`personal.money`、ARPU、ARPPU、修仙产品号或具体测试问题。
- 不使用正则替换作为任意 SQL 的通用修复器。
- 不自动重试权限拒绝、连接失败、超时、用户取消、数据不可用或未知系统异常。
- 不在本次变更中处理会话自动切换、停止按钮残留和埋点存在性误警告等其他页面问题。

## 方案选择

### 方案 A：现有节点内联重试

分别在 `_prepare_sql` 和 `_execute_sql` 内追加生成、校验和重试逻辑。改动表面较小，但会复制修复提示、次数控制、日志和状态处理，并继续扩大两个已有的大函数。

不采用该方案，因为错误处理边界不清晰，难以证明不同入口都重新经过完整校验。

### 方案 B：独立 `repair_sql` 节点

将语法、语义和数据库方言错误转换为统一修复上下文，经条件边进入独立节点。节点只负责向 LLM 请求新的完整 SQL JSON，修复结果必须返回 `prepare_sql` 重新校验。

采用该方案。它能集中管理次数、错误分类、提示词、日志和安全不变量，也便于单元测试每条路由。

### 方案 C：确定性 SQL 自动改写

使用正则或 AST 自动修正已知 `CAST`、递归 CTE 等错误，再继续执行。该方式对极少数固定语法成本较低，但无法处理 Data Skills 业务口径，且可能在语法正确的情况下改变 SQL 业务含义。

不作为主方案。未来若增加确定性规范化，只能处理语义不变且可严格证明的转换，并仍须重新经过全部校验。

## 工作流设计

工作流调整为：

```text
generate_sql
    |
    v
prepare_sql -------- SQL 解析或 Data Skills 错误 --------+
    |                                                   |
    v                                                   v
execute_sql -------- 可恢复数据库语法或方言错误 ---> repair_sql
    |                                                   |
    v                                                   |
generate_chart <------ prepare_sql <---- 修复结果 -------+
```

新增 `repair_sql` 节点以及以下条件路由：

- `prepare_sql` 成功时进入 `execute_sql`。
- `prepare_sql` 识别到可修复错误时写入修复上下文并进入 `repair_sql`。
- `execute_sql` 识别到可修复数据库错误时写入修复上下文并进入 `repair_sql`。
- `repair_sql` 生成新的完整 SQL JSON 后回到 `prepare_sql`。
- 超出预算、重复同一失败或命中不可修复错误时结束并返回明确失败。

## 状态模型

在 `SmartQAGraphState` 中增加：

- `sql_repair_count`：本次工作流已经执行的 SQL 修复次数，初始值为 `0`。
- `sql_repair_reason`：标准错误分类。
- `sql_repair_error`：对用户数据和凭据脱敏后的精确错误信息。
- `sql_repair_failed_sql`：最近一次失败的 SQL。
- `sql_repair_violation`：Data Skills 结构化违规信息；非语义错误时为空。
- `sql_repair_fingerprints`：已经尝试过的错误指纹集合。

修复预算为整个工作流最多 `2` 次，而不是每个节点各 `2` 次。错误指纹由数据库方言、错误分类、规范化 SQL 和规范化错误摘要生成。同一指纹不得再次调用 LLM，避免模型反复生成相同错误并形成循环。

## 错误分类

### 可修复错误

#### `sql_response_format`

LLM 输出无法提取合法 JSON、缺少 SQL 字段或 SQL 为空。修复请求要求返回完整 JSON，不能只返回 SQL 代码块。

#### `sql_parse`

SQL 在 `sqlglot`、只读校验或权限范围解析前无法按当前数据源方言解析，例如 `q043` 的非法 `CAST`。修复上下文包含数据源方言和解析器错误位置。

#### `data_skill_validation`

SQL 违反当前已选 Data Skills 中的必需片段、必需正则、禁止片段或禁止组合。校验保持失败关闭，修复节点只能按规则重写，不能删除或跳过规则。

#### `database_syntax_or_dialect`

SQL 已通过应用层校验，但数据库返回明确的语法或方言错误，例如递归 CTE 列声明、函数签名、类型转换或当前引擎不支持的语法。错误分类必须基于底层异常链，而不是只分析格式化后的 traceback 字符串。

### 不可自动修复错误

- 权限、租户、工作空间、数据源、表、字段或行级访问拒绝。
- SQL 写操作或危险函数校验失败。
- 数据库连接失败、认证失败、服务不可用或连接池异常。
- 查询超时、资源限制、用户取消或任务取消。
- 表、字段、埋点或业务数据确实不存在的 `DataUnavailableError`。
- 无法可靠分类的未知异常。

这些错误沿用现有失败或业务提示路径，不进入 `repair_sql`。

## 结构化 Data Skills 违规

现有 `_data_skill_sql_validation_error` 返回 `str | None`，命中规则后只保留 `message`。设计上增加通用的违规对象，至少包含：

- `message`：面向用户和模型的业务说明。
- `missing_required_contains`：缺失的必需文本片段。
- `missing_required_patterns`：未命中的必需正则。
- `matched_forbidden_contains`：命中的禁止文本片段。
- `matched_forbidden_patterns`：命中的禁止正则。
- `matched_forbidden_groups`：命中的禁止组合。
- `rule_index`：在当前 Data Skill 校验配置中的规则序号，用于日志追踪。

`DataSkillSqlValidationError` 保持现有异常语义，但增加只读 `violation` 属性。现有只关心字符串的调用方继续获得相同 `str(error)`，避免不必要的兼容改动。

核心代码只处理上述通用字段，不解释其中的业务词。具体必需事件、字段和计算规则仍由 datasource-scoped Data Skills 配置提供。

## 修复提示契约

`repair_sql` 向 LLM 传递单独的修复消息，包含：

- 原始用户问题。
- 当前数据源类型及 SQL 方言。
- 最近一次失败的完整 SQL。
- 标准错误分类和脱敏后的原始错误。
- Data Skills 结构化违规信息。
- 本轮已使用修复次数和剩余次数。

消息明确要求：

1. 重写完整 SQL JSON，不输出补丁或局部片段。
2. 不保留已明确冲突的 CTE、字段、事件、分母或语法。
3. 严格使用当前 Data Skills 和当前授权 schema。
4. 不新增未授权表或字段。
5. 只生成一条只读查询。
6. 在输出前自行检查当前数据库方言。

修复调用复用当前 SQL 生成上下文和流式推理能力，但以统一的 `regenerate_sql_after_error_streaming_reasoning` 接口取代仅处理 Data Skills 的专用命名。

## 异常保真与安全

`LLMService.execute_sql` 当前会将多数底层异常包装为只含一层 traceback 的 `AppDBError`。为了可靠分类，包装时必须通过 `raise AppDBError(...) from e` 保留异常链，或者引入携带原始错误类型与安全摘要的专用查询执行异常。不得把数据库连接串、密码、Token、完整用户数据或敏感参数发送给 LLM。

修复 SQL 重新进入 `prepare_sql` 后必须再次调用现有权限与只读校验边界。`repair_sql` 节点不得调用数据库执行器，也不得保存“已校验 SQL”。

## 修仙 Data Skills 调整

通用闭环完成后，仍需补充 datasource 6 的语义示例，使模型首次生成和修复生成更稳定。变更只落在 `tools/seed_xiuxian_data_skills.py` 及其发布链路，不进入共享运行时硬编码。

### 日期补齐

在日期分区 Skill 中增加当前数据源实际验证通过的日期序列范式：

- 若使用递归 CTE，必须符合当前数据库对递归列声明的要求。
- 优先提供不依赖递归 CTE 的、已验证日期骨架，减少数据库方言差异。
- 所有事件或快照大表仍直接使用各自别名的 `dt` 分区条件，不能通过 `bounds` CTE 关联大表。

### 按渠道付费用户

增加按日期、渠道统计 `ServerPayLog` 去重 `uid` 的完整示例。渠道字段来自当前工作空间元数据或已有看板 SQL，不在平台代码中推断替代字段。

### 等级段人均付费

增加等级快照与 `ServerPayLog` 交易明细按用户、业务日期对齐后聚合的示例，明确金额分子使用 `personal.money`，用户分母按问题含义去重，等级字段必须来自当前授权元数据。

### 核心指标综合查询

增加在同一查询中分别计算 DAU、新增用户、付费用户和付费金额的示例，明确每个指标拥有独立事件条件，付费金额和付费用户不能复用 `PayBuyRet` 或 `paytotal`。

发布仍使用现有 datasource-scoped、幂等、带备份和 Embedding 验证的工具链。

## 日志与可观测性

每次修复记录以下结构化信息：

- 工作流、record ID、datasource ID 和租户边界。
- 错误分类、修复次数和错误指纹。
- 进入修复的节点：`prepare_sql` 或 `execute_sql`。
- SQL 校验阶段、数据库执行阶段及最终结果。
- 是否因预算耗尽、重复指纹或不可修复分类停止。

日志不得输出数据库密码、API Key、用户凭据或未脱敏连接参数。前端继续展示最终 SQL 或明确错误，不展示内部规则 JSON 和异常堆栈。

## 测试设计

### 单元测试

- Data Skills 违规对象准确报告缺失的必需项和命中的禁止项。
- 原有 `str(error)` 文本保持一致。
- 非法 `CAST(..., AS DECIMAL)` 被分类为 `sql_parse`。
- 数据库递归 CTE 列别名错误被分类为 `database_syntax_or_dialect`。
- 权限、连接、超时、数据不可用和未知异常不进入修复。
- 相同 SQL 与相同错误指纹不能重复修复。
- 总修复次数不能超过 `2`。

### Graph 测试

- `prepare_sql` 解析失败后进入 `repair_sql`，修复结果重新进入 `prepare_sql`。
- Data Skills 首次失败、修复成功后可以进入执行。
- Data Skills 修复后仍失败时明确终止，不能绕过规则。
- `execute_sql` 可恢复数据库错误后进入修复，并使用新 SQL 成功执行。
- 修复后的 SQL 若触发权限或写操作校验，立即按安全路径失败。
- 流式模式不会重复发送最终 SQL、完成事件或错误消息。

### Data Skills 测试

- 付费 Skill 继续要求 `ServerPayLog`、`$.money` 和 `COUNT(DISTINCT uid)`。
- 继续禁止 `PayBuyRet`、`ed_money` 和 `paytotal` 作为真实收入来源。
- 新增的渠道、等级段和综合指标示例通过语义校验和 SQL 方言解析。
- Skill 仍限定 `tenant_id=7482727237662281728`、`datasource_ids=[6]`。
- 其他工作空间和数据源不能召回或应用这些修仙规则。

### 页面回归

按以下顺序执行：

1. 单独串行重跑 `q025`、`q043`、`q045`、`q048`、`q086`。
2. 检查 SQL、结果、图表、错误提示和修复日志。
3. 五题全部通过后，再通过真实 AI 看板页面串行重跑完整 100 题。
4. 记录成功、真实失败、无数据、耗时、Tokens、会话切换和停止按钮状态。

## 验收标准

- `q025` 不再因递归 CTE 列别名错误失败，并能返回补齐日期后的结果。
- `q043` 不再产生或执行非法 `CAST`。
- `q045`、`q048`、`q086` 最终 SQL 均符合当前 datasource 6 Data Skills，且未使用 `PayBuyRet`、`ed_money` 或 `paytotal` 作为真实收入或付费用户来源。
- 任意修复 SQL 都重新经过 Data Skills、只读、权限和范围校验。
- 同一错误不会无限重试，单次工作流最多调用两次 SQL 修复。
- 不可修复错误不会被误判为可修复，也不会向 LLM 泄露敏感异常信息。
- 完整 100 题回归中不再出现这五类 P0 失败；新发现问题单独记录，不通过静默回退掩盖。

## 预计变更位置

- `backend/apps/chat/task/smart_qa_graph.py`
- `backend/apps/chat/task/llm.py`
- `backend/common/error.py` 或新的 SQL 修复错误模型模块
- `backend/tests/test_smart_qa_graph.py`
- Data Skills 校验器对应测试文件
- `tools/seed_xiuxian_data_skills.py`
- `backend/tests/test_xiuxian_data_skill_seed.py`

实际实施时优先复用现有模块边界；只有在避免循环依赖或控制文件体积确有必要时，才新增独立错误分类或修复上下文模块。
