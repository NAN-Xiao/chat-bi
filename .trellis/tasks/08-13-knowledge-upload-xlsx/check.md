# 检查记录

## 已通过

- `backend/.venv/Scripts/python.exe -m pytest tests/test_knowledge_base_chunking.py tests/test_knowledge_base_publish.py -q`
  - 15 passed。
- `node --test src/views/knowledge-base/KnowledgeSourceUpload.test.mjs src/views/knowledge-base/KnowledgePage.layout.test.mjs`
  - 8 passed。
- `node --test src/views/knowledge-base/KnowledgeBaseV2Panel.row-actions.test.mjs src/views/knowledge-base/KnowledgeSourceUpload.test.mjs`
  - 8 passed，覆盖操作顺序、显式版本选择、上传拒绝消费和 Blob 清理。
- `npm run build`
  - `vue-tsc -b` 与 Vite production build 通过；仅有项目既有的 bundle/dynamic import 警告。
- 本工作区前端在 `0.0.0.0:5190` 启动并返回 HTTP 200；进程命令行确认来自 `D:/AIWork3/chat-bi_ver/frontend`。
- `git diff --check` 通过。
- 修复后定向回归：
  `node --test src/views/knowledge-base/KnowledgeSourceUpload.test.mjs src/views/knowledge-base/KnowledgeBaseV2Panel.row-actions.test.mjs`
  - 9 passed；新增用例验证文件快照、弹窗关闭、编辑器打开、草稿创建、版本刷新和上传的严格时序。
- 修复后 `npm run build` 再次通过；独立 worktree 通过本地目录联接复用主工作区已安装的同版本依赖，未修改依赖清单。
- 更正密码后完成真实浏览器验证：`admin / elex@123` 登录成功；在修复分支前端 `5191` 新建平台公共知识并直接上传 Markdown，页面提示“源文件已解析并保存为知识块，请校验后发布”，编辑器显示 `DRAFT`、正确源文件名、255 个知识块和非空正文。
- 浏览器验证发现纯平台管理员的可选数据源适用性检查返回 403 并中断首次上传。修复为平台管理员在该检查入口提前返回；新增回归后定向测试 10 passed，生产构建再次通过。
- API 只读核验正式草稿：知识库 ID 19，源文件名正确，255 个知识块，空标题 0，启用块空正文 0；首块 `事件：GVGBattleResult`，末块 `事件：OnUpdateEnd`。
- 排查过程中创建的未发布验证草稿 ID 18 无法通过页面或同一 DELETE API 清理，后端返回 `KNOWLEDGE_OPERATION_FAILED`。未绕过服务层直接删除数据库；该草稿未发布、不参与检索，不影响正式草稿 ID 19。

## 扩大检查

- 全部 `test_knowledge_base*.py`：162 passed、7 skipped、2 failed。失败位于 `test_knowledge_base_management_api.py`，分别是并行路由对象缺少 `path`、迁移阶段期望 `LEGACY` 但实际为 `UPGRADING`，与上传/Excel 链路无关。
- 全部知识库前端 Node 测试：28 passed、1 failed。失败是并行加入的归档版本下载逻辑与旧的“不查询 versions”断言冲突；本任务新增测试全部通过。

## 运行环境说明

- 本工作区前端按用户确认使用 `5190`；未操作 `5173`。
- 应用内浏览器访问知识库路由时无登录态，被重定向到登录页，因此未完成真实上传/下载按钮点击；接口回归、前端源码契约测试和构建均已通过。
- 初次提供的密码拼写有误；用户更正为 `elex@123` 后登录成功并完成上述端到端验证。
