# 技术设计

## 数据流

`KnowledgeBaseV2Panel.validateDraft` 只提交版本、修订号、内容 hash 和可选的通用校验 context。后端 `validate_draft` 直接将 body context 转换为 `ValidationContext`，然后交给生命周期服务执行知识内容校验。

## 错误边界

校验入口不再有 datasource_id 相关错误边界，也不在发布前读取数据源状态。知识内容自身的结构和对象声明错误继续由现有 `validate_payload` 返回。

## 兼容性

移除 `ValidateDraftRequest.datasource_id` 字段；保留请求响应格式和通用 `context` 字段，兼容已有内容校验调用。

## 测试策略

- 前端源码回归测试：校验请求不包含 datasource_id。
- 后端单元测试：请求模型和路由不再构建 datasource validation context，仍调用生命周期内容校验。
- 运行后端聚焦测试和前端生产构建。
