# 实施计划

## 阶段 0：基线与清单

- [ ] 固化当前工作区状态，排除用户已有改动。
- [ ] 为旧看板日期、树位置、tracking 配置、加密值和任务 key 增加只读盘点命令或报告。
- [ ] 运行相关后端测试、前端构建和前端静态测试，记录基线。

验证：`git status --short`、后端定向 `pytest`、`frontend npm run build`。

## 阶段 1：权限和数据源边界

- [ ] 删除 `tenant.py` 的第一个租户 fallback，补充无效/未授权租户回归测试。
- [ ] 删除 tracking 配置 `include_legacy` 和未绑定配置合并，补充 datasource scope 测试。
- [ ] 要求看板图表使用明确且已授权的数据源，移除请求参数和看板级 fallback。
- [ ] 更新 API schema、调用方和前端错误展示。

回滚点：阶段 1 单独提交，确认无跨租户测试失败后再继续。

## 阶段 2：看板历史数据迁移与旧格式删除

- [ ] 执行并验证日期筛选 V1 到 V2 迁移。
- [ ] 执行并验证 `pid/sort` 到 `CoreDashboardTree` 迁移。
- [ ] 删除后端 `dashboard_date_filter_legacy.py` 的正常调用路径和 V1 开关。
- [ ] 删除前端 `legacyDateFilter`、旧 pivot 日期字段读取和旧 builder 读取。
- [ ] 将不确定配置改为人工处理错误，不进行猜测修复。

验证：迁移测试、看板加载/编辑/保存路径、V2 配置完整性测试。

## 阶段 3：字段、语义和 embedding

- [ ] 删除字段名、字段类型、字段注释和图表轴的旧名称/第一字段 fallback。
- [ ] tracking Excel 只接受当前模板，更新旧模板测试为明确拒绝。
- [ ] embedding 过期或缺失时返回需要重建的结构化结果，禁止全表检索。
- [ ] 更新 Smart Q&A、分析助手和图表配置器的错误传播。

验证：字段映射、图表配置、embedding 和 SQL 生成定向测试。

## 阶段 4：协议、Redis 和加密

- [ ] 迁移旧加密配置并验证读回，再删除旧 key、旧 ECB 和明文读取。
- [ ] 删除 Redis 任务旧 key 读取，确认任务状态查询仍按租户隔离。
- [ ] 统一 SQL 结果结构，删除 `to_legacy_dict` 及旧结果字段消费者。
- [ ] 删除 SQL 通用方言解析 fallback， unsupported dialect 明确失败。

验证：加密、任务队列、SQL 执行和权限测试。

## 阶段 5：前端清理

- [ ] 删除旧数据源缓存 key 和自动选择第一个数据源。
- [ ] 删除 V1 图表配置和旧字段映射。
- [ ] 删除业务指标的隐式轴/转化率 fallback。
- [ ] 清理浏览器 clipboard legacy 选项；保留普通异常提示。

验证：`npm run build`、前端 `.mjs` 测试、浏览器桌面/移动端路径、无横向溢出。

## 阶段 6：质量检查与规范同步

- [ ] 执行 `trellis-check`，检查跨层数据流和权限边界。
- [ ] 搜索剩余 `legacy`、`fallback`、`include_legacy`、`allow_legacy` 和旧字段名，确认只存在于迁移文档/一次性脚本/测试夹具。
- [ ] 更新 `.trellis/spec/`，记录“业务语义不得静默 fallback”的长期约束。
- [ ] 记录实际验证结果和未覆盖风险。

最终验证：后端测试、前端构建、实际 API 调用、前端运行服务和关键浏览器流程。
