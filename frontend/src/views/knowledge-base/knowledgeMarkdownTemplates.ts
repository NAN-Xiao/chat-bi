import { knowledgeMarkdownTemplateContent } from './knowledgeMarkdownFormat.ts'

export interface KnowledgeMarkdownTemplate {
  readonly id: 'document' | 'business-sql' | 'event-parameters' | 'table-fields-json-path'
  readonly label: string
  readonly fileName: string
  readonly content: string
}

export const knowledgeMarkdownTemplates = [
  {
    id: 'document',
    label: '普通文档',
    fileName: '知识库-普通文档模板.md',
    content: knowledgeMarkdownTemplateContent(`# 示例文档标题（请替换）

> 填写提示：使用标题组织独立主题。二级及以下标题会形成可检索的章节路径，请删除提示并替换示例内容。

## 适用范围

- 适用对象：示例业务团队（请替换）
- 适用场景：示例操作流程（请替换）
- 生效时间：YYYY-MM-DD（请替换）

## 核心说明

在这里填写可独立理解的知识正文。建议一个二级标题只描述一个主题，并补充必要的上下文、定义和限制条件。

### 操作步骤

1. 第一步示例（请替换）。
2. 第二步示例（请替换）。
3. 第三步示例（请替换）。

## 注意事项

- 例外情况：示例例外（请替换）。
- 维护负责人：示例角色（请替换，不要填写账号密码等敏感信息）。
`),
  },
  {
    id: 'business-sql',
    label: '业务术语与 SQL',
    fileName: '知识库-业务术语与SQL模板.md',
    content: knowledgeMarkdownTemplateContent(`# 业务术语与 SQL 示例

> 填写提示：每个业务术语使用一个二级标题，SQL 必须放在 sql 围栏代码块中。请替换示例表名、字段名和统计口径，并在知识库中声明实际引用对象。

## 示例术语：有效订单金额（请替换）

### 定义

统计周期内满足有效状态条件的订单金额合计。请替换为经过业务确认的正式定义。

### 别名

- 示例别名：成交金额（请替换）
- 示例缩写：GMV（请替换）

### 计算口径

- 统计粒度：按天（请替换）
- 时间字段：created_at（请替换）
- 计算公式：SUM(amount)（请替换）
- 过滤条件：仅包含有效状态记录（请替换）
- 空值处理：忽略空金额（请替换）

### 示例问题

最近 7 个完整自然日的有效订单金额是多少？（请替换）

### SQL 示例

\`\`\`sql
SELECT
  DATE_TRUNC('day', created_at) AS statistic_date,
  SUM(amount) AS metric_value
FROM replace_with_order_table
WHERE created_at >= :start_time
  AND created_at < :end_time
  AND status = 'replace_with_valid_status'
GROUP BY DATE_TRUNC('day', created_at)
ORDER BY statistic_date;
\`\`\`

### 使用限制

- SQL 方言：示例为 PostgreSQL（请按目标数据源替换）。
- 时间窗口：使用明确的开始时间和结束时间，避免隐含当前日期。
- 数据权限：查询结果必须遵循当前工作空间和数据源权限。
`),
  },
  {
    id: 'event-parameters',
    label: '事件参数',
    fileName: '知识库-事件参数模板.md',
    content: knowledgeMarkdownTemplateContent(`# 事件与事件参数说明

> 填写提示：每个事件使用一个二级标题，每个参数使用一个三级标题。同一工作空间内事件名必须唯一，请删除提示并替换示例标识。

## 示例事件：order_submitted（请替换）

### 事件说明

- 展示名称：订单提交（请替换）
- 触发时机：用户确认提交后记录一次（请替换）
- 事件时间字段：event_time（请替换）
- 所在明细表：replace_with_event_table（请替换）
- 事件名字段：event_name（请替换）

### 参数：user_id（请替换）

- 展示名称：用户标识（请替换）
- 数据类型：string（请替换）
- 是否必填：是（请替换）
- 说明：标识触发事件的用户，不填写真实用户数据。
- 示例值：example_user（请替换）

### 参数：order_amount（请替换）

- 展示名称：订单金额（请替换）
- 数据类型：decimal（请替换）
- 是否必填：否（请替换）
- 单位：业务币种最小单位（请替换）
- 说明：事件发生时记录的金额。

### 参数值映射：channel（请替换）

| 原始值 | 业务含义 |
| --- | --- |
| example_a | 示例渠道 A（请替换） |
| example_b | 示例渠道 B（请替换） |

## 数据质量约束

- 必填参数缺失时的处理方式：示例说明（请替换）。
- 重复事件识别规则：示例规则（请替换）。
- 延迟上报容忍范围：示例范围（请替换）。
`),
  },
  {
    id: 'table-fields-json-path',
    label: '表字段与 JSON Path',
    fileName: '知识库-表字段与JSON-Path模板.md',
    content: knowledgeMarkdownTemplateContent(`# 表字段与 JSON Path 说明

> 填写提示：每张表使用一个二级标题，普通字段和 JSON Path 使用三级或四级标题。请替换所有示例对象名，并在知识库中声明实际引用对象。

## 示例表：replace_with_table_name（请替换）

### 表说明

- Schema：replace_with_schema（请替换）
- 业务含义：存储示例业务明细（请替换）
- 数据粒度：每行代表一条示例业务记录（请替换）
- 更新时间字段：updated_at（请替换）

### 字段：record_id（请替换）

- 展示名称：记录标识（请替换）
- 数据类型：string（请替换）
- 是否可为空：否（请替换）
- 业务含义：一条业务记录的唯一标识（请替换）

### 字段：payload（请替换）

- 展示名称：扩展属性（请替换）
- 数据类型：JSON（请替换）
- 是否可为空：是（请替换）
- 业务含义：保存结构化扩展信息（请替换）

#### JSON Path：$.items[*].sku（请替换）

- 字段名称：item_sku（请替换）
- 展示名称：商品编码（请替换）
- 返回类型：string[]（请替换）
- 业务含义：提取明细项中的商品编码（请替换）
- 缺失路径处理：返回空数组（请替换）

#### JSON Path：$.source.channel（请替换）

- 字段名称：source_channel（请替换）
- 展示名称：来源渠道（请替换）
- 返回类型：string（请替换）
- 业务含义：提取记录来源渠道（请替换）

##### 值映射

| 原始值 | 业务含义 |
| --- | --- |
| example_a | 示例来源 A（请替换） |
| example_b | 示例来源 B（请替换） |
`),
  },
] as const satisfies readonly KnowledgeMarkdownTemplate[]

export function downloadKnowledgeMarkdownTemplate(template: KnowledgeMarkdownTemplate): void {
  const blob = new Blob([template.content], { type: 'text/markdown;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = template.fileName
  anchor.hidden = true
  document.body.appendChild(anchor)
  try {
    anchor.click()
  } finally {
    anchor.remove()
    setTimeout(() => URL.revokeObjectURL(url), 0)
  }
}
