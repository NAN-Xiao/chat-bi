# AI 看板日期契约修复设计

## 背景

flam 与修仙空间的 100 题真实 UI 测试中，23 条请求在 SQL 执行前被日期契约校验拒绝：15 条 `missing_parameters`、5 条 `database_current_date`、3 条 `metric_chart`。后端拒绝规则符合产品约束，问题来源是工作空间 Data Skill 示例与模型输出契约不一致。

## 目标

- 可变时间范围图表同时生成匹配的 `date_filter` 与 SQL 看板日期 token。
- 固定语义 `metric` 卡不生成 `date_filter`。
- 配置 `date_filter` 的 SQL 不再包含 `CURDATE()`、`NOW()` 或 `CURRENT_DATE`。
- 修复限制在 flam、修仙的工作空间语义配置和通用契约测试，不引入业务字段硬编码或静默字段替换。

## 方案

### 语义源

更新 `tools/seed_flam_first_zombie_data_skills.py` 和 `tools/seed_xiuxian_data_skills.py`：

- 删除或改写会诱导可变时间图表使用数据库当前日期函数的示例。
- 为可变时间图表给出数字日期 token 范式：`{{dashboard_start_yyyymmdd}}`、`{{dashboard_end_yyyymmdd}}`。
- 明确 `date_filter.time_field` 必须对应 SQL 中实际参数化的字段，参数类型必须与 token 家族一致。
- 明确固定“今天”“本月”等单值 `metric` 保留自身时间语义，但省略 `date_filter`。
- 保留固定语义 SQL 使用确定日期边界的能力；禁止规则只针对同时声明 `date_filter` 的 SQL。

### 后端边界

保留 `chat_date_filter.py` 当前严格校验和确定性 `BETWEEN` 重写范围。此次不支持 `dt = ...` 猜测改写、不自动选择其他时间字段，也不移除 `database_current_date` 与 `metric_chart` 拦截。

### 发布与回滚

使用现有幂等 seed 按工作空间和数据源作用域更新对应 Data Skill。发布前导出受影响 `custom_prompt` 记录，发布后回读名称、作用域、数据源与 prompt 内容；发生异常时使用备份恢复对应记录，不影响其他空间或公共 Skill。

## 测试

1. 先增加失败测试，证明 seed 中仍存在与可变看板日期契约冲突的 `CURDATE()` 范式或缺少明确输出约束。
2. 修改 seed 后运行 flam、修仙 Data Skill 目标测试及聊天日期契约测试。
3. 发布到本地系统库后回读验证两个空间的实际 Skill 内容。
4. 通过真实 UI 重跑覆盖三类原失败的代表问题，至少包含：实时趋势、留存趋势、固定 metric。
5. 将结果区分为日期契约通过、SQL 执行错误、图表错误和运行超时；不能用后端单元测试替代 UI 验收。

## 验收标准

- 代表问题不再出现 `missing_parameters`、`database_current_date` 或 `metric_chart`。
- 可变时间图表持久化 SQL 保留 token，执行 SQL 已渲染为实际日期。
- 固定 metric 的持久化配置不包含 `date_filter`。
- 目标自动化测试通过，数据库回读与真实 UI 结果均有可审计证据。
