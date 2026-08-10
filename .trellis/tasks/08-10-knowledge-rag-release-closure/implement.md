# 执行计划

1. 启动任务并加载当前阶段上下文；记录基线分支、工作区状态和运行参数。
2. 检查报告解读入口、请求体和审计落库，执行一次真实鉴权调用；必要时只修复通用链路缺陷并补回归测试。
3. 检查综合分析助手完整链路，使用授权数据源执行一次可计算问题；定位 SQL 探查/生成/执行失败并验证修复。
4. 确认前端服务运行，使用浏览器检查知识库管理、编辑、检索预览和权限页面在三个桌面视口下的布局与交互，保存截图。
5. 使用真实 Worker 标识执行迁移 `status` 和 `verify --compatible-builds-confirmed`，保存原始输出；不执行任何状态变更命令。
6. 运行后端测试、前端构建和必要的定向检查；核对监听端口及 LLM 三项超时参数。
7. 更新任务 implement/check 日志和必要的 Trellis spec；核对主工作区脏文件，提交并推送当前分支，给出是否可合并的结论。

## 实际执行记录（2026-08-10）

- 已通过报告解读真实鉴权调用：`surface=report_interpretation`，检索命中知识库/切片，`semantic_context_audit` 与 `knowledge_retrieval_log` 均有非空记录。
- 已补齐当前工作空间 `datasource_id=6` 的 `event.dt` 结构化元数据：`field_role=partition_date`、`extra_properties.encoding=yyyyMMdd`。未修改共享 SQL 或硬编码业务字段。
- 综合分析助手真实调用成功，返回 2026-08-03 至 2026-08-09 每日 DAU：64、71、54、69、54、52、39，并输出趋势结论；页面显示“已使用知识库（1）”。
- 知识库管理、Skills、看板/助手三个入口在 1366×768、1440×900、1920×1080 下均通过页面级横向溢出检查。
- 迁移只读检查：`status` 显示 `V2_ACTIVE`、`legacy_backfill_remaining=1`、`storage_probe_ready=false`；`verify --compatible-builds-confirmed` 明确未就绪并返回退出码 2。未执行状态变更命令。
- 定向后端回归测试 9/9 通过；前端 `vue-tsc -b && vite build` 通过；运行参数核对为 `120 / 900 / 1`。
- 全量后端测试在独立 worktree 收集阶段失败，原因是主工作区未提交的既有知识库实现未包含在该分支，产生模块导入缺失；不属于本次六个文件修复的回归。
- 已归档验收临时知识库 ID 5，保留 `semantic_context_audit` 与 `knowledge_retrieval_log` 审计记录。

## 关键命令

```powershell
python ./.trellis/scripts/task.py start .trellis/tasks/08-10-knowledge-rag-release-closure
backend\.venv\Scripts\python.exe -m pytest backend/tests
Push-Location frontend; npm run build; Pop-Location
backend\.venv\Scripts\python.exe backend/scripts/knowledge_base_migrate.py status --worker "<worker-id>@<queue-name>"
backend\.venv\Scripts\python.exe backend/scripts/knowledge_base_migrate.py verify --worker "<worker-id>@<queue-name>" --compatible-builds-confirmed
```

## 回滚点

联调修复必须单独提交且可逆；迁移仅读，不产生数据库回滚需求。页面验收发现问题时先修复组件样式/交互并重新构建截图，再进入发布分支整理。
