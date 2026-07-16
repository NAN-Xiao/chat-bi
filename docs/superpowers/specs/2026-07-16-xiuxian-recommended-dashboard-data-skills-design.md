# 修仙推荐看板 Data Skills 设计

## 背景

修仙工作空间绑定数据源 `datasource_id=6`，租户为 `7482727237662281728`。当前推荐看板有 9 个看板、45 个图表组件，其中 44 个组件的抽屉保存了非空结果；“留存分析 / 购买月卡用户的30日留存”结果为空，本次不生成对应 Skill SQL。

系统库当前只有两条修仙 Data Skill：日期分区规则和 PayBuyRet 付费规则。用户已经确认当前真实交易口径以 `ServerPayLog` 为准，因此现有付费 Skill 需要迁移到 `ServerPayLog`，`PayBuyRet` 只保留支付流程事件语义。

只读 `EXPLAIN` 对比已经确认：修仙当前 ADS/MySQL 引擎不会内联一行 `bounds` CTE。`bounds` 写法会为每个受限大表扫描增加 `Values -> Exchange[REPLICATE] -> InnerJoin[Hash Join]`，直接在 `event` 或 `user` 别名上限制 `dt` 不会产生这些节点。推荐看板中有 11 个非空组件仍使用该旧写法。

## 目标

1. 在不改变指标口径和查询结果的前提下，将 11 个旧 SQL 改成每个大表别名直接限制 `dt`。
2. 在任何改写或发布前，备份全部 9 个推荐看板、45 个抽屉的原始 SQL 和完整 `canvas_view_info`。
3. 以 `ServerPayLog` 作为收入、充值订单、付费用户、ARPU 和 ARPPU 的权威交易事件。
4. 将 44 个非空组件按 flam 的业务主题模式拆成多个工作空间 Data Skill，而不是一个超大 Skill 或每组件一个 Skill。
5. 刷新所有新增或更新 Skill 的 embedding，并验证数据源作用域、启用状态和 embedding 签名。
6. 提供可重复执行、可测试、失败时不产生部分发布的工具链。

## 非目标

- 不为结果为空的“购买月卡用户的30日留存”生成 SQL 块。
- 不修改修仙业务库数据。
- 不把修仙口径写入平台全局 Prompt 或其他数据源。
- 不推测 `ServerPayLog` 与 `PayBuyRet` 等价；二者承担不同语义。
- 不重构推荐看板、Data Skill 检索或 embedding 的平台通用实现。

## 权威业务口径

### 日期与分区

- `event.dt`、`user.dt` 为 `YYYYMMDD` 整数分区字段。
- 用户未给日期时，默认查询截至昨天的最近 28 个完整自然日。
- 每个读取 `event` 或 `user` 的别名必须在自身 `WHERE` 或 `JOIN ON` 中直接限制 `dt`。
- 可以使用业务聚合 CTE，但禁止用 `bounds` 派生表向大表提供分区边界。
- 禁止通过 `MAX(dt)` 扫描推断日期边界。

### 付费

- 真实交易事件：`event='ServerPayLog'`。
- 充值金额：`personal.money`。
- 充值订单：`personal.orderId`。
- 商品或礼包：`personal.productid`。
- 付费用户：按 `uid` 去重。
- ARPU 分母使用对应日期的活跃用户；ARPPU 分母使用对应日期的付费用户。
- `PayBuyRet` 只用于支付流程或支付结果事件分布，不得作为收入、真实订单数、付费人数、ARPU 或 ARPPU 的主来源。

## Skill 拆分

保留一个不包含看板 SQL 的共享日期基础 Skill，并生成 12 个看板业务主题 Skill。每个非空组件只归属一个看板主题 Skill；“只归属一个”表示唯一归类，不表示 44 个组件都进入同一个 Skill。

| Skill | 组件数 | 组件 |
|---|---:|---|
| 修仙业务日期与按日聚合口径 | 0 | 共享基础规则，不绑定单个看板组件 |
| 修仙实时付费趋势 | 2 | `eafa54818ed54020a16369a42c99783f`、`d093ae51d20942ffa69bfcea7a14f740` |
| 修仙新增用户总量与系统归因 | 3 | `1c5288d1fe144ddea2b9e82c5ac72b24`、`bdc788729cbc4157bfe3046170c1f92a`、`10d4c025e0bf4d9a9f3bd60194cdabb0` |
| 修仙渠道新增与投放获客 | 5 | `8683537b4c2641afa1cefb2dec8dfb06`、`b687a5175da64fc3a3d37ee9a0ec12b2`、`918d4fd1c4d649d5bae371828928f409`、`96d0dcd61c3a4a9e8a9922d813fce866`、`d03e4b19ba1d4c668c9e6c64b5f16fc9` |
| 修仙 DAU、WAU 与 MAU | 4 | `6b458210dec64fdc8c067b301272f347`、`e4344fa52c564002931ce13ea3657027`、`0369399df2eb4a3299d6d34f9663101b`、`ad88b71e2b08435c8c7a0606c5579f30` |
| 修仙活跃生命周期与维度拆解 | 5 | `fd9a8fe1127e4f21bf1809a6560ec6e2`、`816451c6645a4451b7e85bbfb74d7ee7`、`6c96d753e08742579580d52764d5589b`、`d4675e033a9c4d4881264a66861b066e`、`2ae501be08934d758f82802abf016059` |
| 修仙新增 cohort 留存 | 6 | `f99d0fb5f3624192953bdbfa31549abd`、`531bc723e3cb42f0a1fe2c412d7f05b0`、`57c366462db9418ba14fcde0febeb18d`、`73f88ab0dce848f39037c345e20fe268`、`b0f27793e48349c1a6a7fbf40ff03ffd`、`e797a8af6785452e9fdcee7d80786b6e` |
| 修仙活跃留存与回流 | 1 | `464bc0c1f62049a5b2562fd09d699640` |
| 修仙 ServerPayLog 收入与 ARPU/ARPPU | 5 | `22d89d4a69224e53994d21fb44b376aa`、`2192510609759838208`、`3b585529d8e84bc3ac1ea3bf55746450`、`a6eb26710f7b4dc6ab69ded704c32fee`、`9eff78876b1b405385f96d8559a286a8` |
| 修仙付费用户、渗透与累计付费 | 6 | `95d8497afac14f0a90342031fb43bc04`、`f499305aa9b44a209cbe72cb68985a46`、`304e66bb74254b9e88d8711ce33d94cc`、`e4b33de129da47629caa61612cca8100`、`eba39b8352a34136872404c16fbd17a9`、`fc272fe6a3a74cda90a0564a98890fab` |
| 修仙订单、礼包与支付流程 | 3 | `bcd7dc9ca6c349909fa74c8d4b0502d7`、`ab85f87857774883833dbca9b5ea41ba`、`e65001c16c52433e8afac84c6b2c92a0` |
| 修仙当前等级、付费分层与用户快照 | 2 | `7f71477b49404ad289485f4f22d34c2f`、`3a449b3049314a668661ae65f70e38f1` |
| 修仙英雄养成 | 2 | `99e31069e8b54504a321b7b8066bf946`、`7a582c5a24ab463a8378e43ae63eda83` |

看板主题组件数合计必须严格等于 44，所有 view id 必须唯一。单个 Skill 最多包含 6 个 `dashboard-sql` 块，完整 Prompt 不得超过 15,000 个字符。超过任一限制时发布工具必须失败，不得静默截断或自动塞入其他主题。

## 组件与数据流

### 0. 强制备份门禁

修复工具启动后必须先读取修仙推荐看板当前完整状态，并写入时间戳目录：

`<repo>/.codex-runtime/xiuxian-dashboard-sql-backups/<YYYYMMDD-HHMMSS>/`

备份必须包含：

- 9 个推荐看板的 id、名称、tenant id、datasource id 和完整原始 `canvas_view_info`。
- 45 个抽屉的 dashboard id、view id、标题、原始 SQL、SQL SHA-256、结果是否为空和快照时间。
- 备份清单 `manifest.json`，记录看板数、抽屉数、非空抽屉数、每个文件的 SHA-256 和生成时间。

工具写完备份后必须重新读取文件并验证：看板数严格等于 9、抽屉数严格等于 45、非空抽屉数严格等于 44、所有 SHA-256 与内存中的原始值一致。目录已存在时不得覆盖；备份验证未通过时，不得继续 SQL 等价验证、看板更新或 Skill 发布。

备份目录属于本地运行产物，不提交 Git。恢复时以完整 `canvas_view_info` 为准，抽屉级 SQL 清单用于审计和快速定位差异。

### 1. SQL 修复目录

建立显式的 11 个 view id 修复目录。每条记录保存 view id、原 SQL 签名和改写 SQL，防止看板在实施期间被其他人修改后仍被覆盖。改写只允许：

- 删除日期边界专用 `bounds` CTE。
- 将原边界表达式原样内联到每个 `event`、`user` 别名的 `WHERE` 或 `JOIN ON`。
- 为原 SQL 已读取但未直接限制的同类大表别名补充同一业务窗口的 `dt` 条件。

不允许修改 SELECT 字段、事件名、JSON 路径、JOIN 业务关系、聚合公式、GROUP BY、ORDER BY、LIMIT 或图表字段绑定。

### 2. 结果等价验证器

每个组件在同一数据库会话、同一业务时间窗口下依次执行原 SQL 和改写 SQL。比较过程规范化日期、Decimal、整数、浮点、字符串和 NULL，但不做业务值容差替换。验收条件：

- 字段名称和顺序完全一致。
- 行数完全一致。
- 有 ORDER BY 时逐行逐列完全一致；无稳定顺序时按完整行规范化后的多重集合比较。
- 浮点仅允许数据库驱动序列化造成的等值表示差异，不允许数值误差容差。
- 任一原 SQL 或改写 SQL 超时、报错或结果不一致时，整批失败。

### 3. 执行计划验证器

等价验证通过后，对改写 SQL 执行普通只读 `EXPLAIN`。涉及被修复大表扫描的计划不得再包含由日期边界产生的 `Values -> Exchange[REPLICATE] -> InnerJoin[Hash Join]`。`EXPLAIN` 不作为结果正确性的替代，只作为计划结构门槛。

### 4. 看板事务更新器

强制备份门禁和所有 SQL 验证通过后，在系统库单个事务中按原 SQL 签名做 compare-and-set 更新；任一签名变化或更新数量不是预期值时回滚全部更新。现有修仙 `custom_prompt` 在 Skill 发布前另行追加到同一时间戳备份目录，供 embedding 或发布失败时恢复。

更新后的 `canvas_view_info` 保留组件数据、图表配置、字段绑定和其他元数据，只替换目标 view 的 `sql`。不在本步骤重新生成业务结果快照。

### 5. Data Skill 生成器

生成器从推荐看板当前 `canvas_view_info` 读取 44 个非空组件，使用上表的显式 view id 目录分组。它不得按标题关键词猜测归属。每个 Prompt 包含：

- `data-skill-source:xiuxian:dashboard:<slug>` 唯一标记。
- 修仙工作空间和 datasource 6 作用域声明。
- 主题适用问题、权威事件与字段、指标公式、禁止事项和推荐输出。
- 每个组件的 `dashboard-sql:<view_id>` SQL 块。

现有日期 Skill 使用原 source marker 幂等更新。现有付费 Skill 保留原 source marker 和数据库 id，改名并迁移为 `ServerPayLog` 收入与 ARPU/ARPPU 口径，以免留下互相冲突的旧 Skill。其余主题使用新 marker 幂等 upsert。

### 6. Embedding 刷新

所有新增或更新的 Data Skill 在 upsert 时清空旧 embedding 和签名，然后统一调用现有 `save_custom_prompt_skill_embedding`。保存数量必须等于本次 Skill id 数量。最终逐条验证：

- `tenant_id=7482727237662281728`。
- `type='DATA_SKILL'`、`specific_ds=true`、`datasource_ids=[6]`。
- `active=true`、`visible=true`、`visibility_scope='ADMIN_PUBLIC'`。
- embedding 非空且 `embedding_signature` 与当前 name、description、prompt、模型和维度重新计算的签名一致。

如果 embedding 保存不完整，发布命令返回失败，并用本地快照恢复本次新增或更新的 Skill；已经通过等价验证的看板 SQL 可独立保留，因为它们本身是正确性和性能修复。

## 测试与验收

### 单元测试

- 备份器严格导出 9 个看板、45 个抽屉和 44 个非空抽屉，并验证文件 SHA-256。
- 已存在的时间戳备份目录不可覆盖，备份缺失或校验失败时 apply 流程不能进入验证和更新阶段。
- 44 个非空 view id 全部出现且只出现一次。
- 空组件 `1e4e34743f2d47dfa1c2948742b93a50` 不出现在任何 Skill。
- 12 个看板 Skill 每个最多 6 个 SQL 块、Prompt 不超过 15,000 字符。
- source marker 唯一且 upsert 受 tenant 和 datasource 双重约束。
- 修复后的 SQL 不包含日期边界 `bounds` CTE 关联大表，也不包含 `MAX(dt)`。
- 收入、ARPU、ARPPU SQL 使用 `ServerPayLog` 和 `personal.money`；支付流程分布不得被校验器误判为真实收入。
- 结果规范化和有序/无序比较逻辑覆盖 Decimal、日期、NULL 和重复行。

### 现场验证

- 在任何系统库更新之前，确认本次时间戳备份目录、完整 `canvas_view_info`、45 条抽屉 SQL 和 `manifest.json` 均存在且校验通过。
- 11 对原 SQL 与改写 SQL 全部结果等价。
- 11 个改写 SQL 的 `EXPLAIN` 均通过计划结构门槛。
- 系统库中 11 个目标 view SQL 与经过验证的改写 SQL 一致。
- 44 个组件全部进入明确主题，且无重复归属。
- 13 条修仙 Skill（1 条共享日期基础 Skill和 12 条看板主题 Skill）全部启用、可见、限定 datasource 6，并具有有效 embedding。
- 通过 Smart Q&A 做新增、活跃、留存、收入和英雄养成各至少一个检索冒烟测试，确认能召回相应主题 Skill，且收入 SQL 使用 `ServerPayLog`。

## 失败与回滚

- 备份数量或校验和不一致：立即停止，不执行 SQL 改写验证、系统库更新、Skill upsert 或 embedding 刷新。
- SQL 结果不一致：不更新任何看板，不发布 Skill，输出首个差异组件、字段和行定位。
- 看板 SQL 签名变化：认为存在并发编辑，整批回滚并重新读取。
- Skill 目录缺失、重复或超限：发布前失败。
- embedding 不完整：恢复本次 Skill 变更并保留诊断信息，不把未嵌入的 Skill 视为发布成功。
- Smart Q&A 冒烟测试未召回正确主题：不修改平台通用检索规则，先调整对应 Skill 的名称、描述和主题边界后重新生成 embedding。

## 实施边界

实现应复用仓库现有的系统库配置、数据源解密、Data Skill upsert 和 embedding 保存入口。新增工具只处理修仙租户和 datasource 6，并提供 dry-run 与 apply 两个显式模式；默认 dry-run。dry-run 和 apply 都必须先生成并验证同一轮的原始抽屉 SQL 备份；任何 apply 操作还必须完成等价验证和事务更新前检查。
