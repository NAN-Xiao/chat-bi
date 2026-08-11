# 知识库 RAG 管理与检索可观测性优化

## Goal

消除知识库能力失败时的旧版静默回退，区分空数据与错误，完整传播检索失败状态，并改善知识引用核验信息。

## Requirements

- 当知识库 capability 请求失败时，前端显示明确的加载失败/维护状态，不得自动切换到旧版管理页面。
- 当知识库列表请求失败时，前端显示错误状态和重试入口；真正的空列表才显示空状态。
- 检索结果必须把 `failure_type` 作为结构化运行时状态保留到语义上下文、助手快照和用户可见引用区域。
- 检索预览和聊天引用至少显示知识库名称、版本、章节路径、引用片段和检索状态；不向用户暴露内部 chunk ID。
- 保持当前租户、数据源、权限、版本引用继承和审计契约，不引入跨租户或跨数据源 fallback。
- 不在本任务中启用 V2 发布开关，不修改用户已有的知识库 RAG 改动和无关工作区文件。

## Acceptance Criteria

- [ ] capability 请求失败进入明确错误状态，旧版页面只由服务端明确返回 LEGACY 时使用。
- [ ] 列表请求错误和空列表在桌面页面上可区分，并可重试。
- [ ] 检索失败类型在语义上下文和快照中保留，现有正常检索行为不变。
- [ ] 引用响应和组件支持名称、版本、章节、片段及状态展示，兼容缺失字段的历史快照。
- [ ] 前端知识库相关测试、构建和浏览器路径验证通过；后端定向测试在可用运行环境中执行或记录阻塞原因。
- [ ] Trellis 任务记录实现范围、验证结果和遗留的向量检索性能改造项。

## Notes

- Keep `prd.md` focused on requirements, constraints, and acceptance criteria.
- Lightweight tasks can remain PRD-only.
- For complex tasks, add `design.md` for technical design and `implement.md` for execution planning before `task.py start`.
