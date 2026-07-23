# 平台通用实时事件选表 Data Skill 设计

## 背景

AI 看板在处理“按小时统计今天的新增用户数量”“生成当天实时信息，包括实时收入”等问题时，需要在当前业务日尚未结束的情况下读取实时事件表。现有平台通用时间 Skill 只描述日期窗口，不绑定物理表名；工作空间 Skill 又可能同时包含历史表与实时表 SQL，导致模型获得冲突的选表信号。

本次新增一条独立的平台公开 Data Skill，只定义 `event_realtime` 与 `event` 的条件式选表边界，不把新增、收入等业务指标口径写入平台规则。

## 目标

- 当前授权数据源同时存在 `event` 和 `event_realtime` 时，稳定区分未完成当日查询与完整历史查询。
- “今天、当天、截至目前、实时、当前、按分钟、按小时”等未完成当日问题使用 `event_realtime`。
- 明确历史日期、截至昨天、完整自然日和多日历史趋势使用 `event`。
- 规则同时服务 AI 看板、Smart Q&A 等共用 Data Skill 检索链路。
- 不越过当前工作空间、数据源、Schema 和权限边界。

## 非目标

- 不在平台 Skill 中定义 `UserRegister`、`ServerPayLog`、产品 ID、收入字段或任何业务指标公式。
- 不修改通用 SQL 生成规则、全局 Agent prompt 或前端选表逻辑；仅扩展 Data Skill 的通用适用条件过滤能力。
- 不为缺少实时表或无实时表权限的数据源自动选择其他表。
- 不修改现有 datasource-scoped Data Skill。

## 方案

新增独立的 `PLATFORM_PUBLIC` Data Skill，使用唯一 source marker、结构化 `data-skill-requires-tables` 条件和幂等发布脚本。Data Skill 检索在排序前复用 SQL 权限服务计算当前用户的有效可见表，不满足前置表条件的 Skill 不进入模型上下文。保留现有 Skill 171“不绑定任何表名”的契约，不把物理表规则混入基础日期 Skill。

目标记录属性：

- `tenant_id=1`
- `type=DATA_SKILL`
- `visibility_scope=PLATFORM_PUBLIC`
- `specific_ds=false`
- `datasource_ids=[]`
- `active=true`
- `visible=true`
- `data-skill-requires-tables=["event","event_realtime"]`

## 生效条件与优先级

该 Skill 仅在以下条件全部满足时生效：

1. 当前会话已明确选择一个已授权数据源。
2. 当前数据源的有效授权 Schema 确认同时存在 `event` 和 `event_realtime`；有效表集合由 `build_permission_scope` 综合 `core_table.checked` 与当前用户表级权限得到，缺少任一表时检索层直接排除本 Skill。
3. 工作空间 Data Skill 或事件字典已经提供问题所需的事件名、主体键和指标字段口径。

优先级从高到低为：当前数据源权限与实时 Schema、工作空间元数据及 datasource-scoped Skill、本平台选表 Skill、用户私有偏好。平台 Skill 不能扩大权限，也不能覆盖工作空间的明确配置。

## 选表规则

- 未完成当日：问题包含今天、当天、今日、截至目前、当前、实时，或要求今天按分钟/按小时统计时，查询 `event_realtime`，并使用当前业务日的直接分区条件。
- 完整历史日：问题指定昨天、截至昨天、某个已经结束的日期、完整自然日，或只分析完整历史分区时，查询 `event`。
- 多日趋势：不包含今天的多日趋势查询使用 `event`。
- 包含今天的跨日窗口：已完成历史日期读取 `event`，今天读取 `event_realtime`；只有在指标口径允许合并且字段语义一致时才使用 `UNION ALL`，随后在外层统一聚合，防止重复计算。
- 用户明确指定表名时，仍需先验证当前数据源权限、Schema 和工作空间配置；无权限或不存在时明确报错。

## 禁止回退

当 `event_realtime` 不存在、未授权、缺少所需字段或工作空间未配置业务口径时，不得静默改查 `event`、第一张事件表或相似表名。系统应说明缺失的 Schema、权限或语义配置，并要求用户切换数据源、申请权限或补充工作空间配置。

## Skill 内容边界

Skill 的名称、描述和 prompt 应覆盖“今天、当天、实时、截至目前、按分钟、按小时、实时事件表、历史事件表”等召回词。SQL 示例只展示条件式选表和分区边界，不写具体业务事件名、产品值、收入字段或用户字段。

对于以下问题，平台 Skill 只负责决定使用 `event_realtime`：

- “按小时统计今天的新增用户数量”
- “给我生成当天的实时信息，包括实时收入”

新增用户事件、去重键、收入事件和金额字段继续由当前工作空间的 Data Skill、事件字典及字段元数据提供。

## 发布与恢复

新增 `tools/seed_platform_realtime_event_table_skill.py`：

- 默认 dry-run，只读取并校验现状。
- 显式 `--apply` 才执行写入。
- 使用唯一 marker 定位记录，拒绝重复 marker。
- 使用平台发布锁和 CAS 防止覆盖并发修改。
- 写入前生成备份；写入后刷新 embedding 并回读校验属性、prompt 和 embedding。
- embedding 或回读校验失败时，只恢复本次目标 Skill，不触碰其他平台或工作空间 Skill。

## 测试与验收

自动化测试覆盖：

- 目标 Skill 的平台公开作用域和条件式规则。
- 当前日触发词映射到 `event_realtime`，完整历史触发词映射到 `event`。
- 包含今天的跨日窗口只允许按明确规则合并。
- 实时表不可用时禁止静默回退。
- `required_tables` 满足时保留 Skill，缺少任一表时确定性排除 Skill。
- dry-run 不写库，apply 只写目标记录，失败只恢复目标记录。
- 错误类型/作用域 marker、提交确认丢失、恢复 CAS、解锁异常和 embedding 完整签名校验。

发布后验收：

1. 数据库回读目标记录，确认作用域、唯一 marker、prompt 和 embedding 完整。
2. 分别用两条目标问题执行 Data Skill 检索，确认目标平台 Skill 入选。
3. 在 datasource `6` 的 AI 看板链路中生成 SQL，确认两条问题引用 `event_realtime`，且事件名、字段和产品过滤仍来自工作空间配置。
4. 使用一个不含 `event_realtime` 的数据源验证不会生成伪造表名，也不会静默回退。

## 风险控制

- 平台级召回面较大：通过“双表存在 + 当前数据源授权 + 工作空间业务口径已配置”三个条件限制生效范围。
- 与现有 Skill 冲突：独立 Skill 只决定选表，Skill 171 继续决定时间窗口，datasource-scoped Skill 继续决定业务口径。
- 表结构不同：跨日合并前必须确认字段语义一致，不允许基于相似字段名自动映射。
