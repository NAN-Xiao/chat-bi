# 移除运行时兼容兜底

## Goal

删除平台运行时中会静默替换租户、数据源、字段、图表配置、语义检索、任务状态或加密格式的兼容兜底，使缺失、失效、未授权和旧格式数据都显式失败。

历史数据采用“先一次性迁移，迁移失败记录人工处理，再删除运行时读取分支”的策略。不得通过新的隐式兼容逻辑维持旧数据。

## Requirements

- 收紧租户和数据源边界：无效租户、未授权租户、未明确数据源时直接拒绝，不自动选择第一个可用上下文。
- 删除看板 V1 日期配置、旧树位置、旧图表字段和旧数据源推断的运行时读取；迁移工具可以保留为一次性运维工具，但不得被正常请求路径调用。
- 删除 tracking 配置、字段映射、schema 元数据和图表轴的静默字段替换；配置缺失时返回可识别的校验错误并由调用方清除或提示用户。
- 删除 embedding 失效后的全表检索兜底，改为明确的索引不可用/需要重建结果。
- 统一 SQL 执行结果为标准结构，移除旧 dict 输出和通用 SQL 方言解析兜底。
- 完成旧加密配置、旧 Redis 任务 key 和旧数据源配置的迁移后，删除旧密钥、旧 key 和明文读取分支。
- 删除前端旧数据源缓存、V1 图表配置、旧 builder 读取和业务字段 fallback；保留普通异常处理、权限拒绝和明确的空数据状态。
- 不修改现有知识库 RAG 用户改动及与本任务无关的工作区文件。

## Acceptance Criteria

- [ ] 运行时不再自动替换租户、数据源、字段、图表轴、语义检索结果或旧配置格式。
- [ ] 旧格式在迁移完成后被明确拒绝，错误包含稳定的错误类型或可定位的提示。
- [ ] 租户、数据源、SQL 执行和 embedding 相关回归测试覆盖拒绝路径。
- [ ] 后端定向测试通过，前端构建和现有前端静态测试通过。
- [ ] 实际运行中的 API、前端页面和关键看板路径完成验证，无跨租户读取和页面横向溢出。
- [ ] Trellis 任务记录实现范围、验证结果和本次发现的长期约束。

## Notes

- Keep `prd.md` focused on requirements, constraints, and acceptance criteria.
- Lightweight tasks can remain PRD-only.
- For complex tasks, add `design.md` for technical design and `implement.md` for execution planning before `task.py start`.
