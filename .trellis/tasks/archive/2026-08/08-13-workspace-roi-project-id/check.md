# 工作空间绑定 ROI 项目 ID - 质量检查

## Findings (fixed)

- File: `backend/apps/system/api/tenant.py`, `backend/tests/test_tenant_roi_datasource_binding.py`
- Issue: 默认工作空间表单不提交项目 ID，但编辑路由仍向 CRUD 传入 `None`，可能清空既有值，与审计中的 `unchanged` 不一致。
- Fix: 默认工作空间编辑复用数据库既有值；新增保留值回归测试，并让事务失败测试同时断言项目 ID 回滚。

## Findings (not fixed)

- 后端 `mypy` 无法启动：虚拟环境中的编译扩展名与加载器期望不一致，报 `ModuleNotFoundError: 0aca9ce3d91742c5b361__mypyc`。这是本地工具安装损坏，不是本次代码的类型错误。
- 全量 Ruff 在既有文件上报告 155 项历史问题，主要为未排序导入、`Optional` 语法升级、既有布尔比较和测试 lambda 参数；未批量改写这些非任务代码。`git diff --check` 通过。
- 浏览器已确认本地前端正常渲染且根文档无横向溢出（1280/1280），但当前已登录用户访问 `/system/tenant` 被权限路由重定向，无法执行平台管理员创建/编辑抽屉和移动视口验证。

## Verification

- Lint: partial pass. `git diff --check` 通过；全量 Ruff 因上述既有 155 项问题未通过。
- TypeCheck: frontend pass (`npm run build` 包含 `vue-tsc -b`)；backend unavailable due broken local `mypy` installation.
- Tests: pass. 显式 `PYTHONPATH=<repo>/backend` 后，目标后端测试 54 项通过；`Tenant.roi.test.mjs` 通过。
- Migration: pass. `alembic heads` 返回单一 `157workspaceprojectid (head)`；upgrade/downgrade SQL 契约测试通过。
- Runtime: pass. 标准端口 `5173/8000/8001` 属于其他工作区，本任务未停止或接管；当前工作区前端 `5179`、API `8005`、MCP `8006` 均监听正常，Worker 使用 `local-DONGJINCHAO-chat-bi_ver` 队列运行。健康检查分别为前端 `200`、API 登录方法端点 `401`、MCP 根路径 `404`，均符合预期。
- Database: pass. 迁移前备份为 `.codex-runtime/pg-backups/zhishu_bi_2.0.0-20260813_104519.dump`；核心数据库已升级到 `157workspaceprojectid`，确认 `roi_project_id` 为 `VARCHAR(128) NULL`。
- LLM config: pass. `LLM_REQUEST_TIMEOUT=120`、`LLM_TASK_MAX_WAIT_SECONDS=900`、`LLM_MAX_RETRIES=1`。
- Build: pass. 前端生产构建完成。
