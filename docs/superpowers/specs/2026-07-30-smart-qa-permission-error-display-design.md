# 智能问数权限错误展示修复设计

## 问题

图表数据接口会返回结构化失败数据，例如：

```json
{
  "status": "failed",
  "error_type": "permission_denied",
  "message": "没有查看权限"
}
```

当前前端仅把响应保存到 `record.data`，而页面统一错误组件读取 `record.error`，导致权限失败没有进入标准错误展示链路。

## 方案

在 `applyChartDataResponseToRecord` 中统一归一化图表数据响应：

- 始终保留原始响应到 `record.data`。
- `status === 'failed'` 时，把非空 `message` 或 `reason` 写入 `record.error`。
- 权限失败缺少消息时，使用明确的“没有查看权限”兜底。
- 后续成功或业务提示响应清除旧的 `record.error`，避免任务重试成功后仍残留错误。
- 存在 `record.error` 时不挂载图表块，避免统一错误组件与图表业务警告重复展示。
- 保留已有 `business_notice` 行为，不改变后端协议或图表数据结构。

该入口同时被实时 SSE 后的数据加载、任务恢复和记录刷新复用，因此无需在多个组件分支重复处理。

## 验证

先扩展 `chat-chart-data-response.test.mjs`，验证权限失败写入错误、成功响应清除错误以及错误状态不挂载图表块，再实现最小逻辑并运行该回归测试、前端类型检查与构建。
