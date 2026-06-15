# 智能报表图表分析/预测入口临时隐藏备忘

记录日期：2026-06-15

## 背景

智能报表生成图表后，图表回答下方原本会显示“数据分析”和“数据预测”两个入口。

当前产品方向是：

- 智能报表只负责提问、生成 SQL、返回数据和生成图表。
- 图表后的进一步分析和预测，后续统一交给“综合分析助手”承接。
- 因此这两个入口目前只是临时隐藏，不是删除功能。

## 当前实现

前端入口位置：

```text
frontend/src/views/chat/index.vue
```

当前通过固定开关隐藏入口：

```ts
const showChartAnalysisPredictActions = false
```

模板中只有当该开关为 `true` 且当前回答存在图表时，才会渲染“数据分析 / 数据预测”按钮。

## 必须保留的内容

以下内容暂时不要删除，除非后续明确决定彻底下线该能力：

- `clickAnalysis(...)`
- `clickPredict(...)`
- `AnalysisAnswer.vue`
- `PredictAnswer.vue`
- `analysis_record_id`
- `predict_record_id`
- 相关前后端 API、数据结构和历史消息展示逻辑

原因：历史对话中可能已有分析/预测记录；后续也可能需要恢复入口，或改造成从“综合分析助手”调用同一套能力。

## 恢复方式

如果后续需要重新显示智能报表图表下方的“数据分析 / 数据预测”入口，只需把：

```ts
const showChartAnalysisPredictActions = false
```

改为：

```ts
const showChartAnalysisPredictActions = true
```

然后运行前端类型检查：

```bash
npm exec vue-tsc -- -b --force
```

## 注意事项

- 不要把这个临时隐藏误判为废弃代码清理。
- 不要删除“综合分析助手”相关能力。
- 如果后续要彻底迁移分析/预测链路，应先确认历史消息兼容、接口依赖、权限控制和助手侧调用方式。
