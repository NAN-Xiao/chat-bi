# 知识库版本发布、任务恢复与迁移设计

## 1. 文档定位

本文是 `knowledge_base_rag_development_design.md` 的生命周期专项配套设计，补齐以下实现约束：

- 草稿、校验、发布、失败和回滚的数据库状态转移。
- 同一条目并发编辑和版本号分配。
- Redis 入队失败、Worker 崩溃和超时恢复。
- 旧 `/knowledge-base/save` 与 V2 版本体系的兼容边界。
- API 与 Worker 的文件共享前提。
- DDL 迁移与文档向量回填的分离。

发生冲突时，本文对版本状态、发布任务和迁移的描述优先于主开发文档中的概述。

## 2. 数据库完整性

### 2.1 主记录与版本指针

`knowledge_base` 保留三个版本指针：

- `draft_version_id`：当前唯一可编辑版本。
- `current_version_id`：当前唯一线上版本。
- `publishing_version_id`：当前发布作业认领的版本。

约束：

1. 三个指针必须引用同一 `knowledge_base_id + tenant_id` 下的版本，不能只建立到 version 主键的弱外键。
2. `current_version_id` 只能指向 `PUBLISHED`；`publishing_version_id` 只能指向 `PUBLISHING`。
3. 发布期间 `draft_version_id` 与 `publishing_version_id` 指向同一版本；成功后两者同时清空。
4. 发布失败后清空 `publishing_version_id`，`draft_version_id` 保留失败版本，允许修改后重新校验。
5. 主记录删除使用受控服务完成；外键和 cascade 不能删除仍被问答引用或审计记录引用的发布版本。

`knowledge_base_version` 增加唯一约束 `(id, knowledge_base_id, tenant_id)` 供复合外键使用，并保留 `(knowledge_base_id, version_number)` 唯一约束。

复合外键只负责证明版本归属，不能证明被引用版本的状态。三个指针的状态不变量使用 PostgreSQL `DEFERRABLE INITIALLY DEFERRED` constraint trigger 在事务提交时校验：

- `current_version_id` 非空时，目标版本必须属于同一 knowledge/tenant 且最终状态为 `PUBLISHED`。
- `publishing_version_id` 非空时，目标版本必须属于同一 knowledge/tenant 且最终状态为 `PUBLISHING`。
- `draft_version_id` 非空时，目标版本必须属于同一 knowledge/tenant 且最终状态属于活动草稿集合。
- constraint trigger 同时挂在主记录指针变化和版本归属/状态变化上，防止只修改版本状态绕过校验。
- 发布切换、失败收敛和回滚建草稿必须在一个事务中形成最终合法状态；不得用普通即时 trigger 校验事务中间态，也不得只依赖服务层检查。

使用 PostgreSQL partial unique index 保证同一条目最多一个活动草稿：

```text
status IN (
  DRAFT, VALIDATING, VALIDATION_FAILED,
  READY_TO_PUBLISH, PUBLISHING, PUBLISH_FAILED
)
```

### 2.2 版本号分配

创建新草稿、回滚复制和迁移补建版本时：

1. `SELECT knowledge_base ... FOR UPDATE` 锁定单条主记录。
2. 在同一事务内读取当前最大 `version_number` 并分配 `max + 1`。
3. 插入版本并条件更新 `draft_version_id`。
4. 唯一约束冲突转换为中文并发提示；不把数据库异常原文返回页面。

不得在无主记录行锁的情况下用应用层 `max + 1` 分配版本号。

回滚目标确定后仍需先锁定主记录。条目已经存在任一活动草稿时拒绝回滚，返回 HTTP 409、机器码 `KNOWLEDGE_DRAFT_ALREADY_EXISTS` 和中文消息“该知识已有未发布草稿，请先处理当前草稿后再回滚。”；不得覆盖、复用或静默删除已有草稿。只有没有活动草稿时才复制历史版本形成下一版本草稿。

## 3. 状态转移

| 当前状态 | 操作 | 新状态 | 指针变化 |
| --- | --- | --- | --- |
| 无草稿 | 新建/编辑已发布条目 | DRAFT | 创建新版本并设置 draft |
| DRAFT/VALIDATION_FAILED/PUBLISH_FAILED | 保存 | DRAFT | revision + 1，保留 current |
| DRAFT | 校验 | VALIDATING | draft 不变 |
| VALIDATING | 校验成功 | READY_TO_PUBLISH | draft 不变 |
| VALIDATING | 校验失败 | VALIDATION_FAILED | draft 不变 |
| READY_TO_PUBLISH | 创建发布作业 | PUBLISHING | 设置 publishing=draft |
| PUBLISHING | 发布成功 | PUBLISHED | current=该版本，draft/publishing 清空，旧 current=SUPERSEDED |
| PUBLISHING | 发布失败/终止 | PUBLISH_FAILED | current 不变，publishing 清空，draft 保留 |
| 历史版本 | 回滚 | DRAFT | 复制为新版本并设置 draft |

规则：

- 保存、校验和发布都携带 `draft_version_id + revision + content_hash` 并使用条件更新。
- `VALIDATING` 和 `PUBLISHING` 期间不允许保存、删除、归档或回滚。
- 对 PUBLISH_FAILED 再次编辑必须先 `revision + 1` 并转为 DRAFT，旧发布作业不能认领新 revision。
- 成功切换 current、旧版本转 SUPERSEDED、新版本转 PUBLISHED 和清理指针必须位于同一短事务。
- 发布版本一旦进入 PUBLISHED 或 SUPERSEDED，payload、正文、源文件引用和对象引用均不可修改。

## 4. 数据库发布作业

### 4.1 `knowledge_publish_job`

Redis 任务不是发布状态的权威来源。新增数据库作业表：

| 字段 | 说明 |
| --- | --- |
| `id` | 作业 ID |
| `tenant_id/knowledge_base_id/version_id` | 发布边界 |
| `revision/content_hash` | 被认领的不可变草稿快照 |
| `status` | QUEUING/QUEUED/RUNNING/SUCCEEDED/FAILED/CANCELLED |
| `task_id` | Redis task ID，可空 |
| `enqueue_attempts/last_enqueue_at` | 入队确认次数和最近尝试时间 |
| `attempt/max_attempts` | 领域重试次数 |
| `heartbeat_at/deadline_at` | 存活和过期判断 |
| `stage` | PARSE/NORMALIZE/CHUNK/EMBED/FINALIZE |
| `error_code/error_message` | 安全错误 |
| `create_by/create_time/update_time` | 审计 |

唯一约束：同一 `version_id + revision + content_hash` 最多一个未终结作业。数据库中的作业、`publishing_version_id` 和版本状态共同构成最终权威。

### 4.2 创建和入队

`POST /knowledge-base/{id}/publish`：

1. 在数据库事务中 CAS 校验当前草稿为 READY_TO_PUBLISH。
2. 创建 QUEUING 作业，设置版本 PUBLISHING 和主记录 `publishing_version_id`。
3. 提交后调用注册任务队列，dedupe key 使用 publish job ID；队列接口返回 `ENQUEUED/REJECTED/UNKNOWN` 三态结果，不以是否抛出普通异常直接推断结果。
4. `ENQUEUED` 时将作业 CAS 为 QUEUED 并保存 `task_id`。
5. 只有任务名未注册、配额校验在任何 Redis 写入前明确拒绝等确定性 `REJECTED` 才立即执行失败收敛；配额检查必须先于 dedupe 和任务记录写入。
6. Redis 超时、连接中断或响应丢失等无法证明任务未写入的异常一律视为 `UNKNOWN`：保留 QUEUING，记录安全错误码和最近入队时间，向页面返回“发布任务正在确认中，请稍后查看状态。”，由对账任务确认或修复，不能反向标记失败。
7. 进程若在步骤 2 和步骤 4 之间退出，由对账任务识别超时 QUEUING 作业并确认已有任务、修复原任务或失败收敛。

队列可能在 API 完成步骤 4 前就把任务交给 Worker。Worker 因此允许 CAS `QUEUING/QUEUED -> RUNNING`，并在 `task_id` 为空时写入当前 Redis task ID。API 的 `QUEUING -> QUEUED` CAS 未命中时必须重新读取作业；若作业已由同一任务推进到 RUNNING 或 SUCCEEDED，则视为入队成功，不能反向标记失败或覆盖 Worker 状态。已有不同 task ID 的活动作业按 stale task 拒绝，并交由对账任务处理。

现有 `enqueue_task` 的 Redis task 记录、dedupe 键、主队列和 pending 索引不是单条原子写入。第一期需在 `task_queue.py` 增加幂等的确认入队/修复能力，以 Lua 或等价原子操作保证一个 PENDING task 同时存在于任务记录和可消费队列；对账任务发现孤立 PENDING task 时修复原 task 的队列项，发现任务记录不存在或已终结时才创建新 task。不得仅再次调用相同 dedupe key 后因返回旧 PENDING 记录就判定已成功入队。即使 Lua 已原子执行，客户端也可能在服务端成功后丢失响应，因此原子入队不能替代 `UNKNOWN` 状态和后续确认。

新发布链路禁止降级到 FastAPI `BackgroundTask`，也禁止在 API 进程内直接执行 Embedding。

### 4.3 Worker 执行

Worker 使用作业 ID 加载领域状态：

1. 携带当前 Redis task ID，CAS `QUEUING/QUEUED -> RUNNING` 并增加 attempt；`task_id` 为空时同时认领，已被其他活动 task 认领时幂等退出。
2. 验证 tenant、version、revision、content hash、PUBLISHING 状态和指针全部匹配。
3. 每完成一个外部步骤更新 `heartbeat_at` 和 `stage`；每个 Embedding 批次开始前和返回后，都以 `status=RUNNING`、截止时间、版本指针、revision 和 content hash 为条件刷新心跳。
4. Embedding 在数据库事务外执行。
5. 最终短事务再次验证所有 CAS 条件，写入 chunk 和对象引用，切换 current 并完成状态转移。
6. 业务异常由 publisher 捕获并执行统一失败收敛；异常原文只写服务端日志。

批次心跳条件更新未命中表示作业已被对账任务终止、超时或失去版本所有权。Worker 必须立即停止后续解析/Embedding，不得继续调用外部模型，也不得写入 chunk、对象引用或版本指针；已生成但未提交的临时结果直接丢弃。

Redis 条目级锁只保护任务 claim 和 finalize 的短临界区，TTL 不覆盖整个 Embedding 过程。锁名使用 `tenant_redis_key(...)`；锁过期不能解除数据库 CAS 约束。

## 5. 崩溃和超时恢复

新增注册任务 `knowledge_base.reconcile_publish_jobs`，Worker 启动时执行一次，并按固定周期执行：

- QUEUING 超过入队确认期限：先按 publish job dedupe key 查询任务记录和可消费队列；任务完整时补写 task_id/QUEUED，任务部分存在时原地修复，确认不存在时才在 enqueue_attempts 未耗尽的前提下创建新任务，无法确认时继续保持 QUEUING 并告警。达到确认截止时间后仍无法证明任务存在或不存在时才以 CAS 失败收敛。
- QUEUED 的 Redis task 不存在或已终结失败：按领域重试次数重新入队或失败收敛。
- RUNNING 的 `heartbeat_at` 超过 `KNOWLEDGE_PUBLISH_TIMEOUT_SECONDS`：先确认 Redis task 和数据库作业均过期，再以 CAS 标记失败；后续 Worker 批次检查会发现状态已终结并停止。
- 数据库作业已经终结但 Redis stale recovery 再次投递：Worker 幂等返回，不重复写 chunk 或切换版本。
- 发现主记录 `publishing_version_id` 与活动作业不一致：记录审计告警并失败关闭，不猜测应发布的版本。

统一失败收敛必须在事务中完成：job=FAILED、version=PUBLISH_FAILED、清空 publishing、保留 draft/current。对账任务本身必须幂等，多 Worker 同时运行时只有一个 CAS 成功。

## 6. 旧接口兼容与写路由权威

### 6.1 权威状态矩阵

`knowledge_migration_state.phase` 是写路由的最高权威，环境开关只能控制 V2 能力是否对页面开放，不能降低数据库阶段或重新开放旧写：

| 数据库 phase | 旧写接口 | V2 写接口 | 环境开关语义 |
| --- | --- | --- | --- |
| `LEGACY_OPEN` | 允许，且事务内持有迁移状态共享锁 | 拒绝并提示升级尚未完成 | `true` 也不能提前启用 V2 写 |
| `CUTOVER_BARRIER` | 临时拒绝 | 临时拒绝 | 任意开关值都不能绕过屏障 |
| `V2_ACTIVE` | 永久返回 410 | 开关为 true 时允许 | 开关为 false 只关闭 V2 管理写，绝不恢复旧写 |

非法组合必须失败关闭并记录告警。例如 `phase=V2_ACTIVE` 且管理开关关闭时，页面进入维护态，新 V2 写返回中文“知识库管理暂时不可用，请稍后重试。”，旧 `/save` 仍返回 410。`KNOWLEDGE_RUNTIME_CONTEXT_ENABLED` 独立控制 AI 运行时是否使用新知识，但只有 `V2_ACTIVE`、索引完整且双读校验通过后才允许开启。

### 6.2 V2 激活后的旧接口

- 前端只调用新草稿、校验、发布和版本 API，并通过服务端能力响应确认当前管理模式，不根据本地开关猜测数据库阶段。
- 旧 `POST /knowledge-base/save` 一律拒绝写入，返回 HTTP 410、机器码 `KNOWLEDGE_LEGACY_WRITE_DISABLED`，中文消息“知识库已升级，请刷新页面后重新操作。”。
- 不把缺少 revision 的旧更新请求自动转换为新草稿，不允许其覆盖源文件或绕过发布状态机。
- 原 `DELETE /knowledge-base/{id}` 路径切换到 V2 删除/归档语义，不能继续物理删除已发布版本。
- V2 列表和详情只读当前版本表；旧主表 content/file 字段仅作为迁移来源。

滚动部署不能依赖前后端或所有后端实例在同一时刻切换。必须先部署兼容版本，使全部 API 和旧解析 Worker 都识别数据库 phase 并遵守共享锁，再执行回填与数据库切换；前端 V2 页面只能在兼容后端已全量就绪后开放。

## 7. 文件存储部署前提

当前 `AppFileUtils` 将文件存入本地 `UPLOAD_DIR`，发布 Worker 通过同一路径读取。第一期明确约束：

- API 和 Worker 必须运行在同一机器，或挂载同一个可读写共享目录，且 `UPLOAD_DIR` 解析到相同物理文件。
- 启动检查使用真实跨进程握手：数据库单例探针记录保存当前 generation、配置指纹、token hash 和更新时间；API leader 持有数据库行锁，只有配置指纹变化或显式轮换命令才创建新 generation 和探针文件。普通 API 实例启动只读取当前 generation，不得各自轮换。
- 每个准备消费发布队列的 Worker 必须读取当前 generation 对应文件、校验内容哈希，再按 `generation + worker_id + queue_name` 回写心跳。API 只在发布队列的所有活动消费者都有当前代新鲜回执时接受文档发布；扩缩容期间发现没有回执的新消费者时失败关闭。
- generation 轮换后旧回执立即失效；轮换事务必须串行，多个 API 并发启动不能互相覆盖 generation。仅比较配置路径、API 自读文件、随机投递一次且只被某个 Worker 消费的探针任务，或 API/Worker 各自在本地创建文件均不算共享验证。
- 数据库只保存不可猜测的 file ID 和文件元数据，不保存客户端路径。
- 文件只能通过鉴权 API 访问，不能公开 `UPLOAD_DIR` 静态目录。
- 多机器生产部署前必须迁移共享文件系统或对象存储；对象存储仍不属于本期实现。

该约束同时适用于上传临时文件、历史版本源文件和发布解析文件。

## 8. 迁移与回填

### 8.1 Alembic 只执行确定性 DDL

Alembic 中禁止执行以下操作：

- 调用 Embedding 或 LLM 网络服务。
- 解析 Word、生成 chunk 或读取 `UPLOAD_DIR` 文件。
- 向 Redis 队列入队。
- 依赖运行时用户权限或外部业务数据源在线状态。

迁移按职责拆分，编号以实施时实际 head 为准：

```text
153_knowledge_base_version_lifecycle.py
154_knowledge_base_retrieval_projection.py
155_semantic_permission_epoch.py
```

153 创建版本、发布作业、数据库迁移状态和主记录指针；154 创建 chunk、对象引用、对象解析、Skill 投影状态、适用性和审计表；155 创建权限 epoch，并扩展权限类型所需字段或索引。

### 8.2 幂等数据回填

新增独立注册任务或管理脚本 `knowledge_base.backfill_v2`：

1. 按主键游标分页扫描旧 `knowledge_base`。
2. 每次读取同时记录旧行的 `update_time`、`file_id` 和标准化正文 `content_hash`，以 `legacy_id + source_fingerprint` 作为稳定迁移键；旧行未变化时重复执行不生成重复版本，旧行已变化时创建下一迁移版本而不修改已发布版本。
3. READY 且正文非空的记录迁移为 PUBLISHED，同时设置独立 `index_status=PENDING`，不立即进入新 RAG。
4. PENDING/PROCESSING/FAILED 迁移为草稿并保留安全错误摘要。
5. 单独入队解析、chunk 和 Embedding；最终写入前再次按旧行 `update_time + file_id + content_hash` 做 CAS 校验，来源已变化时放弃本次切换并把该行放回增量队列。
6. 记录扫描游标、成功数、跳过数和失败原因，支持暂停和续跑。
7. 所有 READY 数据完成索引并通过双读抽样后，才允许打开 `KNOWLEDGE_RUNTIME_CONTEXT_ENABLED`。

回填失败不得阻止 DDL 部署，也不得修改旧线上 `content/file_id`。迁移窗口内旧运行路径继续服务。

### 8.3 在线追平与切换屏障

数据库处于 `LEGACY_OPEN` 时旧 `/knowledge-base/save` 仍可能更新源记录，不能依靠一次全量扫描完成切换。新增单例表 `knowledge_migration_state` 作为数据库权威状态，至少包含 `phase=LEGACY_OPEN/CUTOVER_BARRIER/V2_ACTIVE`、扫描游标、最近追平时间、revision 和更新时间；所有后端实例不得用进程内变量判断切换阶段。

切换流程：

1. 先完成兼容版本滚动部署：所有 API、任务 Worker 和可能执行旧 `BackgroundTask` 的实例都必须识别迁移状态；部署清单和 Worker 心跳中记录 build/version，发现旧版本实例时禁止进入屏障。
2. `LEGACY_OPEN` 阶段运行全量回填并持续增量追平；旧写接口以及旧 `knowledge_base.process_document` Worker/BackgroundTask 的每一次状态或正文写回，都必须在各自写事务内读取并持有迁移状态行共享锁，写入和状态检查属于同一事务。
3. `LEGACY_OPEN` 下为保持旧页面行为，可以继续创建经过屏障包装的 FastAPI `BackgroundTask`；进入 `CUTOVER_BARRIER` 后旧写入口先被拒绝，因此不再创建新任务。已有旧任务要么在屏障前排空，要么在每次状态/正文写回时因无法通过 phase 检查而失败关闭，不能在 V2 激活后迟到写旧正文或状态。
4. 待差异收敛后，切换任务以排他锁把状态改为 `CUTOVER_BARRIER`。该锁会等待已开始的受控旧写完成，并阻止新旧写穿过屏障。
5. 屏障期间新旧写均返回 `KNOWLEDGE_UPGRADE_IN_PROGRESS`，中文消息“知识库升级中，请稍后重试。”；已有读取继续服务。切换任务再次确认不存在不识别屏障的 API/Worker，并确认旧解析任务已排空或全部具备失败关闭能力。
6. 在上述条件满足后执行最终增量扫描、来源指纹 CAS、索引完整性和双读校验。任一记录未追平或索引失败时不得开启 V2，可回到 `LEGACY_OPEN` 修复后重试。
7. 全部校验通过后，在数据库中原子切换为 `V2_ACTIVE`。服务端写路由立即按数据库 phase 生效，再开放前端 V2 页面；此后旧 `/save` 无论环境开关为何值都按 6.2 节返回 410 中文升级提示。

该流程保证屏障前已提交的旧写被最终扫描覆盖，屏障后的旧写不会遗漏；不得通过部署时约定“短时间无人编辑”代替数据库切换屏障。

## 9. 文件改造范围

新增：

```text
backend/apps/knowledge_base/version_repository.py
backend/apps/knowledge_base/lifecycle_service.py
backend/apps/knowledge_base/publish_jobs.py
backend/apps/knowledge_base/publisher.py
backend/apps/knowledge_base/reconciliation.py
backend/apps/knowledge_base/backfill.py
backend/apps/knowledge_base/cutover.py
backend/apps/knowledge_base/storage_probe.py
backend/alembic/versions/153_knowledge_base_version_lifecycle.py
backend/alembic/versions/154_knowledge_base_retrieval_projection.py
backend/alembic/versions/155_semantic_permission_epoch.py
backend/tests/test_knowledge_base_state_machine.py
backend/tests/test_knowledge_base_publish_recovery.py
backend/tests/test_knowledge_base_legacy_api.py
backend/tests/test_knowledge_base_backfill.py
backend/tests/test_knowledge_base_cutover.py
backend/tests/test_knowledge_base_storage_probe.py
```

修改：

```text
backend/apps/knowledge_base/api/knowledge_base.py
backend/apps/knowledge_base/tasks.py
backend/common/core/task_registry.py
backend/common/core/task_queue.py
backend/common/core/config.py
tools/worker-local.ps1
tools/stack-local.ps1
```

API 路由按管理、版本和发布职责拆分；模型按主记录/版本、检索投影和审计拆分。不得把全部新路由和表模型继续堆入现有单文件。

## 10. 必测场景

- 两个请求并发创建下一草稿时只产生一个活动草稿和唯一版本号。
- 发布成功后 current 正确切换，draft/publishing 清空，旧 current 转 SUPERSEDED。
- 发布失败后 current 不变、publishing 清空、失败草稿仍可继续编辑。
- DB 作业提交后 API 崩溃，对账任务能重新入队或失败收敛。
- Redis 仅写入 task/dedupe 记录但尚未写入可消费队列时，对账能修复原 PENDING task，不会被 dedupe 返回值误判为已入队。
- Redis 已完成原子入队但响应丢失时，API 保持 QUEUING，对账确认同一任务后推进状态，不会把正在执行或已成功的作业标记失败。
- Worker 在 Embedding 中崩溃，超时后不会永久卡在 PUBLISHING。
- Worker 在 API 写入 QUEUED 前抢到任务仍能正确认领，API 不会把 RUNNING/SUCCEEDED 作业回退或标记失败。
- 对账任务终止超时作业后，仍在运行的 Worker 会在下一 Embedding 批次检查时停止外部调用和最终写入。
- 过期 Redis 任务再次投递不能重复写 chunk 或覆盖新版本。
- 数据库进入 `V2_ACTIVE` 后旧 `/save` 不能更新正文、文件或状态，并返回中文提示。
- `V2_ACTIVE + KNOWLEDGE_MANAGEMENT_V2_ENABLED=false` 不会重新开放旧写；`LEGACY_OPEN + true` 也不会提前开放 V2 写。
- 多 API 实例并发启动不会轮换出多个探针 generation；任一活动发布 Worker 未完成当前代回执时不能接受发布任务。
- Alembic 在无网络、无 Redis、无上传目录的环境中可以完成 DDL。
- 回填任务重复执行不生成重复版本、chunk 或对象引用。
- 旧写与回填并发时来源指纹 CAS 能发现变化；进入切换屏障后不遗漏屏障前写入，也不接受新的旧接口写入。
- 屏障前启动的旧 Worker/BackgroundTask 在最终扫描后尝试迟到写回时失败关闭，不会修改旧源记录或造成 V2 漏迁。
- 已有活动草稿时回滚被明确拒绝，且延迟约束在事务提交时阻止任何指针指向错误状态版本。
