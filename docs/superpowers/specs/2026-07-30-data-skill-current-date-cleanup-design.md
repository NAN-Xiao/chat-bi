# Data Skill 数据库当前日期清理设计

## 目标

消除 flam 与修仙 Data Skills 对 `CURDATE()` 等数据库当前时间函数的主动诱导，避免其与平台看板日期参数契约冲突。

## 行为边界

- 可转存看板的非 `metric` 时序查询使用完整 `date_filter`，SQL 使用与字段类型匹配的看板日期 token。
- 固定语义 `metric` 不返回 `date_filter`，也不使用看板日期 token；其固定日期语义由问题和 SQL 字面量表达。
- 实时“今日”规则保留业务时区含义，但示例不得把数据库会话的 `CURDATE()` 当作业务日期来源。
- “禁止使用 `CURDATE()`”等说明文字保留，不计为主动诱导。

## 修改范围

- 更新 `tools/seed_flam_first_zombie_data_skills.py` 与 `tools/seed_xiuxian_data_skills.py` 的规则和示例。
- 更新对应种子测试，增加主动用法扫描回归。
- 运行两个幂等发布流程并刷新 embedding。
- 查询系统库，确认启用 Skills 中仅剩禁止性说明，不再存在主动 SQL 用法。

## 验证

- 先运行新增测试并观察其因现有 `CURDATE()` 主动用法失败。
- 修改种子后运行两个数据源的完整种子测试。
- 发布后查询 `custom_prompt`，分类检查 `CURDATE()` 命中上下文。
- 复跑日期校验与 SQL 修复回归，确保运行时严格校验仍有效。
