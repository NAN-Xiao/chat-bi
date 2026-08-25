# 执行清单

1. 更新 `KnowledgeBaseV2Panel.vue` 和 API 类型，移除校验请求中的 datasource_id。
2. 更新知识库草稿校验请求模型和路由，移除 datasource_id 分支及 validation context 构建调用。
3. 增加前后端回归测试，覆盖请求不携带 datasource_id 且仍执行内容校验。
4. 运行后端聚焦 pytest、前端相关 Node 测试和 `npm run build`。
5. 使用 Trellis quality check，记录结果并更新必要规范。

## 验证记录

- `backend/tests/test_knowledge_base_validate_request.py`、`test_knowledge_base_payload_validation.py`、`test_knowledge_base_state_machine.py`：34 passed。
- `frontend/src/views/knowledge-base/KnowledgeBaseV2Panel.row-actions.test.mjs`：10 passed。
- 前端完整 `npm run build` 未能在隔离工作树执行：该工作树没有可解析的前端依赖，外部 `vue-tsc` 运行还生成了临时 JS 文件，已清理；未发现本次改动导致的构建错误。
