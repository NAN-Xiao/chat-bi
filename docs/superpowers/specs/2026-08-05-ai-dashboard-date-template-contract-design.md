# AI 看板日期模板契约修复设计

## 目标

AI 看板针对“今天”“最近 N 天”等明确日期范围生成非 `metric` 图表时，必须保存可复用的日期模板 SQL 和对应 `date_filter`。执行阶段再把模板渲染为实际日期。实时事件表与历史事件表遵循同一日期参数契约，不再因实时表身份默认固化日期。

## 范围

- 修正平台 Data Skill 282、283 与 flam Data Skill 230 的冲突和错误占位符。
- 保持平台 Data Skill 281 作为通用日期模板基准，不改变默认日期逻辑。
- 在 Smart Q&A SQL 校验层拒绝明确日期范围的非 `metric` 图表缺少 `date_filter` 或日期 token 的响应，并复用现有日期配置修复流程。
- 保留 `metric` 固定语义例外；不改变无日期范围查询、数据源权限、表选择和默认过去七天逻辑。
- 不硬编码 `event_realtime`、`dt`、产品 ID 或游戏业务口径到共享校验代码。

## 语义层设计

### Skill 281

保持现有内容。它继续定义：可转存时序图保存日期 token，执行时再解析实际边界，固定语义 `metric` 不套用看板日期范围。

### Skill 282

保留“明确当天事件查询选择实时事件表”的选表职责。将“直接限制当前业务日分区”改为引用通用日期契约：非 `metric` 时序图保存成对日期 token 与 `preset=today`，不得保存固定 `yyyyMMdd`；固定语义 `metric` 仍可保持自身语义。

### Skill 283

取消“实时查询默认不套用历史日期 pivot”的全局否定。将 `partition_date` 和 `realtime_partition` 纳入可参数化日期角色；只要当前 Schema 提供字段及日期编码，明确日期范围的非 `metric` 图表就可返回 `date_filter`。`realtime_date_policy` 仅用于数据源明确配置的额外限制，不再作为使用 token 的前置条件。

### Skill 230

把单层 `{dashboard_start_yyyymmdd}` / `{dashboard_end_yyyymmdd}` 修正为双层 token，并明确当天实时非 `metric` 时序图同样保存模板。

所有 Skill 修改必须落在对应幂等 seed 脚本中，并通过脚本同步数据库后按 ID、租户、内容标记和 token 做独立回读。

## 后端契约设计

在 `normalize_chat_date_filter_for_question()` 的入口基于用户问题和图表类型判断是否明确要求日期模板：

- 图表类型不是 `metric`；
- 问题包含现有受支持的明确日期表达式，即“今天/今日/当天”或“最近/近/过去 N 天”。

满足以上条件时：

- 缺少 `date_filter` 时抛出 `missing_date_filter`，无论 SQL 是否已经包含 token；
- `date_filter` 存在时继续复用现有字段、参数类型、成对 token、当前日期函数和日期表达式校验；
- “今天”统一覆盖模型日期表达式为 `preset=today`；
- 校验失败进入现有 `DATE_FILTER_CONFIGURATION` SQL 修复节点，不增加新的修复通道。

无明确日期范围的问题继续沿用当前默认过去七天逻辑，但只有模型提供 `date_filter` 时才启用；本次不扩大该行为。

## 数据流

```text
问题 + Schema + Data Skills
  -> LLM SQL JSON
  -> 日期模板契约校验
     -> 合法：保存模板 SQL + chart.pivot
     -> 非法：DATE_FILTER_CONFIGURATION 修复
  -> 权限和 SQL 校验
  -> 执行前临时渲染日期
  -> 保存结果与图表
```

## 错误处理

- 明确日期非 `metric` 响应缺少配置时使用现有 `missing_date_filter` 错误，保证现有错误分类器可识别。
- 修复次数、指纹去重和失败消息保持现有约束。
- 不自动猜测时间字段、参数类型或数据源日期字段；模型必须依据当前 Schema 和 Skill 返回完整配置。

## 测试

- 单元测试先复现截图问题：今天按小时、`line`、固定 `yyyyMMdd`、无 `date_filter` 必须失败。
- 覆盖最近 N 天无配置、无日期范围查询、固定语义 `metric`、合法当天实时模板。
- Skill seed 测试验证 282/283/230 的新文案、合法双层 token 和旧冲突文案消失。
- 回归 Smart Q&A 日期测试、Data Skill 冲突/SQL 校验测试和相关看板日期测试。
- 数据库同步后读取 Skill 230/281/282/283，确认内容与 seed 一致且作用域不变。

## 非目标

- 不修改普通看板默认日期范围。
- 不恢复实时表只能查询当天的限制。
- 不迁移或改写历史 ChatRecord；已有固定日期记录保持原样。
- 不调整 Schema、打点字典或无关 Data Skill 的检索排序。
