# 修仙 PayBuyRet 付费与 ARPPU 语义修复设计

## 背景与根因

修仙工作空间绑定 `tenant_id=7482727237662281728`、`datasource_id=6`。当前仅配置了“修仙业务日期与按日聚合口径” Data Skill，没有收入、付费人数和 ARPPU 的业务口径。

当用户询问“近七天 ARPPU”时，模型只能根据表字段猜测，将 `user.pay.paytotal` 这一累计付费快照误用为当日收入，并将累计付费用户误作当日付费用户，得到约 118 至 120 的稳定近似值。该结果不代表当日每付费用户平均收入。

修仙事件字典和业务库样本已经确认：

- 成功支付事件为 `PayBuyRet`，事件展示名为“支付付款成功”。
- 当次人民币金额为 `event.personal` 的 `$.ed_money`。
- 成功标识为 `event.personal` 的 `$.ed_isSuccess`。
- 支付平台订单号配置为 `event.personal` 的 `$.ed_orderId`，但当前抽样窗口内值为空。
- `event.personal` 中存在 `$.ed_payId`，但其值会被多个用户和多笔支付复用，不是唯一交易号，不能代替订单号。
- `user.pay.paytotal` 是累计快照，只适用于累计付费、LTV 或付费分层，不能直接作为当日收入。

## 目标

为修仙数据源新增工作空间级、数据源级 Data Skill，使智能问答和其他共享语义服务在生成收入、付费人数和 ARPPU SQL 时使用同一套已验证口径，并通过确定性 SQL 校验阻止再次使用 `paytotal` 计算当日 ARPPU。

## 语义口径

### 适用范围

- 仅适用于修仙工作空间 `datasource_id=6`。
- 适用于付费金额、收入、流水、付费用户、付费次数和 ARPPU。
- 不定义 ARPU、付费率等依赖活跃用户分母的指标；这些指标必须在活跃事件口径另行确认后再扩展。

### 数据来源

- 明细表：`event`。
- 事件条件：`event = 'PayBuyRet'`。
- 成功条件：`JSON_UNQUOTE(JSON_EXTRACT(personal, '$.ed_isSuccess')) IN ('true', '1')`。
- 正金额条件：解析后的 `personal.ed_money > 0`。
- 人民币金额：`CAST(NULLIF(JSON_UNQUOTE(JSON_EXTRACT(personal, '$.ed_money')), '') AS DECIMAL(18, 4))`。
- 付费用户标识：`uid`。
- 业务日期：整数分区字段 `dt`，继续遵守现有日期 Data Skill。

### 指标定义

- 当日付费金额：成功且正金额的 `PayBuyRet` 事件 `ed_money` 求和。
- 当日付费用户数：成功且正金额的 `PayBuyRet` 事件按 `uid` 去重计数。
- 当日付费次数：成功且正金额的 `PayBuyRet` 事件行数。由于订单号为空，名称必须明确为“付费事件次数”，不能展示为“去重订单数”。
- 当日 ARPPU：当日付费金额除以当日去重付费用户数，分母为零时返回 `NULL`。
- `pay.paytotal`、`allianceinfo.paytotal` 不得用于当日付费金额、当日付费人数或 ARPPU。

## 查询与图表行为

- “近七天”表示以数据源最大可用业务日期为结束日期、向前包含七个自然日；不得只返回有支付事件的日期。
- 趋势 SQL 应补齐自然日序列。无付费日期的付费金额和付费用户数返回 0，ARPPU 返回 `NULL`，避免用 0 伪装“每位付费用户收入为零”。
- SELECT 中的日期按现有 Data Skill 输出为 `YYYY-MM-DD`，图表横轴绑定日期字段。
- 图表至少保留 ARPPU；需要辅助解释时可同时输出付费金额和付费用户数，但不得用累计付费人数替代当日付费人数。
- 周/月透视时 ARPPU 不直接求和或平均，必须用该周期成功付费金额除以该周期去重付费用户数重新计算。

## 实现范围

### Data Skill 种子

在 `tools/seed_xiuxian_data_skills.py` 的 `DATA_SKILLS` 中新增“修仙付费收入与 ARPPU 口径”：

- 使用独立且稳定的 `data-skill-source:xiuxian:paybuyret-monetization-arppu` 标记。
- 写入上述事件、字段、过滤、公式和日期补齐规则。
- 提供可直接复用的 MySQL 8 参考 SQL。
- 保持现有幂等 upsert 和 embedding 刷新流程不变。

### 确定性 SQL 校验

在 Data Skill 注释元数据中增加针对“ARPPU、付费金额、付费用户、收入、流水”等问题的校验规则：

- 要求 SQL 包含 `PayBuyRet`、`ed_money` 和 `ed_isSuccess`。
- 当问题是当日/趋势 ARPPU、收入或付费人数时，禁止 SQL 使用 `paytotal` 作为指标来源。
- 校验失败时返回明确的修复说明，不静默替换字段。

### 回归测试

新增修仙 Data Skill 种子测试，至少验证：

- Skill 作用域固定为 `tenant_id=7482727237662281728`、`datasource_id=6`。
- Skill 包含 `PayBuyRet`、`personal.ed_money`、`personal.ed_isSuccess`、`COUNT(DISTINCT uid)` 和 ARPPU 公式。
- Skill 明确禁止使用 `paytotal` 计算当日收入、当日付费人数和 ARPPU。
- Skill 明确规定订单号为空时不得把 `ed_payId` 当唯一交易号。
- 幂等 upsert 不影响现有日期 Data Skill。

## 数据更新与验证

1. 先运行目标单元测试，确认新增测试在实现前失败。
2. 修改修仙 Data Skill 种子并运行目标测试、相关语义校验测试和静态检查。
3. 执行 `tools/seed_xiuxian_data_skills.py`，将新 Skill 写入系统库并刷新 embedding。
4. 查询系统库确认两个修仙 Data Skill 均为活动、可见、仅绑定 datasource 6。
5. 使用截图问题重新生成 SQL，确认不再引用 `paytotal`，并对最近业务窗口执行只读对账。

## 抽样验收基线

在 2026-07-09 至 2026-07-14 的只读样本中，正确结果为：

| 日期 | 成功付费金额 | 付费用户数 | ARPPU |
| --- | ---: | ---: | ---: |
| 2026-07-09 | 3613 | 18 | 200.72 |
| 2026-07-10 | 158 | 4 | 39.50 |
| 2026-07-11 | 167 | 3 | 55.67 |
| 2026-07-12 | 0 | 0 | NULL |
| 2026-07-13 | 0 | 0 | NULL |
| 2026-07-14 | 30 | 1 | 30.00 |

## 验收标准

- 新生成的修仙 ARPPU SQL 使用 `PayBuyRet.personal.ed_money` 和 `COUNT(DISTINCT uid)`。
- SQL 同时过滤成功标识和正金额，不再用 `paytotal` 推导当日收入或当日付费用户。
- 最近七天趋势补齐七个自然日；零付费日 ARPPU 为 `NULL`。
- 抽样窗口结果与上述基线一致。
- 新 Skill 只作用于 datasource 6，其他数据源行为不变。
- 种子可重复执行，embedding 刷新成功，相关测试通过。

## 暂不处理

- 不修改全局提示词、通用后端逻辑或前端图表组件。
- 不把 `ed_payId` 声明为订单号或唯一交易号。
- 不在本次修复中定义 ARPU、付费率、LTV 或退款口径。
- 不回写或修造业务库中的空 `ed_orderId`；订单级去重需要数据生产方提供稳定唯一交易号后再单独设计。
