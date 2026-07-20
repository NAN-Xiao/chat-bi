# 修仙实时付费 Data Skill 定向同步设计

## 背景

修仙工作空间的“实时看板”已更新为单一组件 `2193936101973073920`，标题为“每小时付费数据”。该组件使用数据源 `6` 的 `event_realtime` 表，按小时同时输出支付记录数和收入金额。

现有 Data Skill `269`（`修仙实时付费趋势`）仍引用两个已经退出当前看板的历史组件：

- `eafa54818ed54020a16369a42c99783f`：每小时支付记录数。
- `d093ae51d20942ffa69bfcea7a14f740`：每小时累计支付记录数。

本次只同步 Data Skill，不修改当前看板及其 SQL。

## 目标

- 保留 Skill ID `269`、名称、source marker 和工作空间作用域。
- 将 `realtime-payment` 主题的组件来源更新为 `2193936101973073920`。
- 将 Skill SQL 和业务说明同步为当前看板的实际口径。
- 刷新对应 embedding，并验证内容一致性和问题召回。
- 保证后续运行生成器时不会恢复为旧组件内容。

## 业务口径

- 数据表：`event_realtime`。
- 真实交易事件：`event = 'ServerPayLog'`。
- 产品条件：沿用当前看板的 `prod = 110000047`。
- 支付记录数：`COUNT(*)`。
- 收入金额：汇总 `personal.money`，空字符串、JSON `null` 和 SQL `NULL` 不计入金额，最终空聚合显示为 `0`。
- 小时维度：沿用当前看板 SQL，以事件毫秒时间戳经 `FROM_UNIXTIME(time / 1000)` 后格式化为 `%H:00`。
- 日期条件：Skill 中保留当前看板已保存 SQL，不自行改写日期或时区口径。

## 实现方案

1. 更新 `xiuxian_dashboard_skill_catalog.py` 中 `realtime-payment` 主题，将两个旧组件 ID 替换为当前组件 ID，并更新主题说明和业务指导。
2. 让现有 `build_data_skills` 从当前推荐看板快照提取该组件 SQL，继续生成相同 marker 的 Skill。
3. 使用现有 marker 驱动的幂等更新逻辑定向更新 Skill `269`，不新增重复 Skill。
4. 发布前保存 Skill 269 当前内容；事务失败或 embedding 校验失败时恢复旧内容。
5. 其他 12 个 Skills、其他看板和业务 SQL均不写入。

## 验证标准

- 生成结果仍为 13 个修仙工作空间 Skills，marker 唯一。
- `realtime-payment` 仅包含一个 `dashboard-sql` 块，组件 ID 为 `2193936101973073920`。
- Skill SQL与当前看板 SQL字节一致。
- Skill 269 仍为 `ADMIN_PUBLIC`、`specific_ds=true`、`datasource_ids=[6]`、`tenant_id=7482727237662281728`。
- Skill 269 不再包含两个旧组件 ID，也不再包含旧 `event` 表实时 SQL。
- embedding 刷新成功且维度符合当前模型配置。
- “每小时支付记录数和收入金额”等问题能够召回 `修仙实时付费趋势`。
- 相关单元测试、格式检查和差异检查通过。

## 风险与控制

- 当前推荐看板快照已由 45 个旧组件变为包含新组件的实时状态，完整发布器的旧白名单可能拒绝。实现时先用测试更新目录契约，再执行定向发布，避免无关 Skill 被重写。
- 看板在读取和写入之间可能再次变化。发布时校验看板 ID、组件 ID、SQL摘要和更新时间；不一致则中止，不覆盖新内容。
- embedding 刷新失败不能留下半更新状态。使用既有备份与恢复机制，验证失败即恢复 Skill 269。
