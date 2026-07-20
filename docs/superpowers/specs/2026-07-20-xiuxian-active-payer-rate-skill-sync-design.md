# 修仙活跃用户付费率看板与 Data Skill 同步设计

## 背景

修仙工作空间 datasource 6 的核心看板组件
`95d8497afac14f0a90342031fb43bc04` 已改为“近15日活跃用户付费率趋势”。
当前 SQL、图表标题、Y 轴和结果快照已经使用新口径，但组件顶层 `fields`
仍残留旧字段“累计付费率”，对应工作空间 Data Skill 也尚未同步。

目标是让看板配置、可重复发布源和线上 Data Skill 使用同一份业务口径，
同时避免影响修仙工作空间其他 12 条 Data Skill。

## 业务口径

- 数据源：修仙 datasource 6。
- 产品：`prod = 110000047`。
- 时间范围：最近 15 个完整自然日，即昨天减 14 天至昨天，共 15 天。
- 活跃用户：当天存在 `UserActive` 事件的去重 `uid`。
- 活跃付费用户：当天同时存在 `UserActive` 和 `ServerPayLog` 事件的去重 `uid`。
- 活跃用户付费率：活跃付费用户数除以活跃用户数，再乘以 100，保留两位小数。
- 该指标是每日比率，不是累计付费率。

## 变更范围

### 看板组件

仅更新核心看板 `afe201c9762c448aa0495f3508c01793` 的组件
`95d8497afac14f0a90342031fb43bc04`：

- 标题保持“近15日活跃用户付费率趋势”。
- SQL 保持已在 datasource 6 验证通过的严格用户交集写法。
- 顶层 `fields` 更新为“日期、活跃用户数、活跃付费用户数、活跃用户付费率”。
- X 轴绑定“日期”，Y 轴只绑定“活跃用户付费率”。
- Y 轴语义使用 `metricType=ratio`、`pivotAggregation=avg`。
- 删除与当前手写 SQL 不一致的旧 SQL Builder 状态，避免后续误生成旧口径 SQL。
- 保留当前正确的结果快照和 SQL 数据源配置。

### Data Skill

仅更新 source marker 为
`data-skill-source:xiuxian:dashboard:payer-penetration` 的工作空间 Data Skill：

- 从同步后的看板快照重新生成组件
  `95d8497afac14f0a90342031fb43bc04` 的标题、字段与 SQL 块。
- 在主题规则中明确活跃用户、活跃付费用户和每日比率口径。
- 明确该组件不得使用 `user.pay.paytotal` 或“全部用户快照”作为分母。
- 主题内其他 5 个累计付费或付费维度组件保持原口径和 SQL 不变。
- 保持 `specific_ds=true`、`datasource_ids=[6]` 和现有工作空间可见范围。

## 发布策略

采用定向事务同步，不执行 13 条 Data Skill 的全量发布：

1. 只读回查目标看板、目标组件和目标 Skill，校验唯一性及更新时间。
2. 在 `.codex-runtime` 下分别备份完整看板 JSON 和目标 Skill 记录。
3. 在事务中以 CAS 条件更新看板组件，防止覆盖并发修改。
4. 基于更新后的看板快照重新生成 `payer-penetration` Skill。
5. 以 source marker 唯一定位并更新目标 Skill，其他 Skill 不写入。
6. 提交后刷新目标 Skill Embedding；Embedding 失败时恢复看板与 Skill 备份。
7. 回读并验证看板 SQL 与 Skill 内嵌 SQL 字节一致。

## 失败处理

- 目标看板、组件或 Skill 不唯一时停止，不做写入。
- 看板更新时间或原始内容与预读不一致时 CAS 失败并停止。
- SQL 执行、字段校验、Skill 生成或事务写入任一步失败时回滚数据库事务。
- Embedding 或发布后回读失败时按备份恢复目标看板与 Skill，并报告恢复结果。
- 不使用兼容字段回退，不把旧“累计付费率”自动映射到新字段。

## 验证标准

- SQL 在 datasource 6 返回最近 15 个完整自然日的 15 行数据。
- SQL 执行不超过应用 60 秒超时；目标参考值为当前实测约 1 秒。
- SQL 使用 `prod = 110000047`，不包含 `110000038`。
- 看板顶层字段、结果字段、X/Y 轴字段均不存在旧“累计付费率”。
- 目标 Skill 恰好包含组件 `95d8497afac14f0a90342031fb43bc04`
  的一个 SQL 块。
- Skill SQL 与看板 SQL 字节一致，且包含新标题和新输出字段。
- 目标 Skill Embedding 签名和向量已刷新。
- 使用“近15日活跃用户付费率”检索时能够命中目标 Skill。
- 其他 12 条修仙 Data Skill 的 ID、Prompt 和 Embedding 签名保持不变。

## 不在范围内

- 不修改其他看板或组件。
- 不修改其他 12 条修仙 Data Skill。
- 不改变 `ServerPayLog` 收入、ARPU、ARPPU 或累计付费快照口径。
- 不引入 datasource 3 或产品 `110000038` 的配置。
- 不修改通用平台 SQL 生成、图表渲染或权限逻辑。
