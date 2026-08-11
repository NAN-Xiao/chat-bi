# 实施记录

## 修改范围

- 将 `Settings.KNOWLEDGE_MANAGEMENT_V2_ENABLED` 默认值改为 `True`。
- 本地 API、Worker 与 stack 编排默认写入 `true`，新增 `-DisableKnowledgeManagementV2` 显式回滚参数。
- 保留 `-EnableKnowledgeManagementV2` 兼容入口，同时传入 enable/disable 时明确拒绝启动。
- 保持 runtime context 与 retrieval 默认关闭。
- 同步配置测试、PowerShell 编排测试、上线手册、开发设计和 backend runtime spec。

## 验证结果

- `test_knowledge_base_legacy_api.py` + `test_knowledge_base_cutover.py`：21 项通过。
- `test_stack_local_script.py`：23 项通过。
- `ruff check`：通过。
- 三个 PowerShell 脚本语法解析：通过。
- `compileall` 与 `git diff --check`：通过。
- `ruff format --check` 报告三个既有 Python 文件需要整体格式化；本任务未执行整文件格式化，避免带入无关格式变化。

## 数据与环境

- 未修改 `knowledge_migration_state`、知识库数据或远程环境。
- 测试期间临时创建的 `backend/.venv` 目录联接已移除，目标虚拟环境未修改。
