# 数据字典运维维护说明

## 目标

数据字典中的“字典字段”是工作空间级语义配置，用来同时服务：

- LLM SQL 生成：作为字段角色、业务含义、SQL 约束和表达式说明。
- 图表配置器：作为可选择字段、时间字段、分组字段、指标字段和 SQL 表达式来源。

它不修改物理业务库结构。物理建表、加列、改列仍走“新增字段/结构变更申请”。

## 运维维护流程

1. 进入“系统管理 -> 数据字典”，选择当前工作空间绑定的数据源和表。
2. 新项目冷启动时，点击“下载模板”。模板会按当前绑定数据源的真实物理表生成业务 sheet。
3. 已有配置批量维护时，点击“导出当前配置”，在 Excel 中修改字段说明、来源字段、JSON 路径、表达式、事件等列，再点击“导入配置”上传。
4. 少量维护时，使用“新增字典字段”或表格行里的“修改字典”。
5. 如果要新增或修改真实库表字段，使用“新增字段/修改”，它只提交结构变更申请，不会直接执行 DDL。
6. 如果某个字典字段不应再给 LLM SQL 或图表配置器使用，点击“删除”字典字段。删除只移除工作空间语义配置，不删除物理数据库字段。
7. 保存或导入后刷新数据字典或重新进入图表配置器，确认字段来源、展示别名、表达式符合预期。

## Excel 导入导出

数据字典页面提供三个 Excel 操作：

- 下载模板：生成通用模板，业务 sheet 对应当前数据源真实表，运维在这些 sheet 里补充语义字段。
- 导出当前配置：把当前工作空间 tracking config 导出成同样结构，适合批量修改后回传。
- 导入配置：解析平台模板或兼容 `#事件数据`、`#公共事件属性`、`#用户数据` 的竞品格式，并合并到当前配置。

导入是合并操作，不会因为 Excel 只包含一部分字段就清空其它已有配置。合并键是：

- 表：`table_name`
- 字段：`table_name + field_name`
- 事件：`event_name`

导入后同一份配置会被两类能力读取：

- 图表配置器通过 `schema-metadata` 和 `fieldList` 读取字段展示名、来源字段、JSON 路径、表达式。
- LLM SQL 通过工作空间 tracking prompt context 读取字段角色、字段说明、事件映射、表达式和 AI 说明。

导入时如果发现字段没有 `source_field/json_path`、来源字段不在物理表中、或无法为当前数据源生成 JSON SQL 表达式，会返回警告。警告不应忽略：这些字段虽然会被保存，但可能不会出现在图表字段列表中，或需要运维手动补 `expression`。

## 字段类型

- 物理字段：来自数据源真实表结构，例如 `event.ext`、`event.time`、`user.pay`。
- 字典字段：运维维护的逻辑字段或 JSON 子字段，例如 `ext.ed_ccu`、`pay.paytotal`、`userinfo.country`。
- 嵌套字段视图：某张真实表内部按 JSON 来源字段分组的视图，例如 `event` 表下的 `ext`、`personal`、`deviceinfo`。它不是物理表，也不应出现在左侧表列表中。

字典字段必须挂在一个真实表下面，并且它的来源字段必须存在于物理表中。比如 `event.ext.ed_ccu` 对应：

- 表名：`event`
- 字段名：`ext.ed_ccu`
- 来源字段：`ext`
- JSON 路径：`$.ed_ccu`
- 表达式：``JSON_UNQUOTE(JSON_EXTRACT(`event`.`ext`, '$.ed_ccu'))``

如果物理字段本身叫 `event`，并且里面存的是 JSON 字符串，也按同样方式维护：

- 表名：`event`
- 字段名：`event.xxx` 或一个更友好的逻辑名。
- 来源字段：`event`
- JSON 路径：`$.xxx`
- 表达式：``JSON_UNQUOTE(JSON_EXTRACT(`event`.`event`, '$.xxx'))``

在数据字典页面里，左侧只选择真实表；右侧通过“JSON: 来源字段”切换嵌套字段视图。要让某个来源字段出现在嵌套视图中，需要满足任一条件：

- 该物理字段的语义类型或字段角色被维护为 JSON，例如 `semantic_type=json`、`field_role=event_params_json`。
- 已经存在至少一个字典字段指向它，例如 `source_field=event`、`json_path=$.xxx`。

## 推荐字段结构

每个字典字段至少维护：

- `table_name`：物理表名。
- `field_name`：逻辑字段名，JSON 子字段建议用 `source.path`，例如 `ext.ed_ccu`。
- `source_field`：实际承载 JSON 文本的物理字段，例如 `ext`、`personal`、`event`、`payload`。
- `json_path`：JSON 路径，例如 `$.ed_ccu`、`$.payload.amount`。如果 `field_name` 已写成 `source.path`，系统会按点号推断；但运维手动维护时建议显式填写。
- `aliases`：展示别名，第一项会作为图表配置器里的显示名。
- `field_role`：字段角色，例如 `event_time`、`partition_date`、`event_name`、`subject_id`、`json_path_dimension`、`json_path_metric`。
- `semantic_type`：语义类型，例如 `date`、`timestamp_ms`、`identifier`、`category`、`number`、`boolean_flag`、`json`。
- `expression`：当前数据源方言的 SQL 表达式。图表配置器生成 SQL 时会使用它。
- `field_comment`：业务说明，LLM 会读取。
- `ai_notes`：生成 SQL 的注意事项，适合写口径禁忌和边界条件。

同一个字段配置会被两类能力消费：

- LLM SQL：读取字段角色、语义类型、来源字段、JSON 路径、别名、说明、示例值、SQL 表达式和 AI 说明。
- 图表配置器：读取字段名、展示名、语义类型、来源字段、JSON 路径和 SQL 表达式，用来生成可执行 SQL。

## 不同数据源表达式

表达式必须按当前数据源方言填写，不要跨库复用。

MySQL / Doris / StarRocks 常见 JSON：

```sql
JSON_UNQUOTE(JSON_EXTRACT(`event`.`ext`, '$.ed_ccu'))
```

PostgreSQL JSONB 常见写法：

```sql
("event"."ext"::jsonb ->> 'ed_ccu')
```

ClickHouse 常见写法：

```sql
JSONExtractString(ext, 'ed_ccu')
```

Excel/CSV 导入表如果已经是普通列，不需要 JSON 表达式；可直接把字段角色和展示别名维护在物理字段上。

## 运维原则

- 优先通过“数据字典 -> 新增字典字段/修改字典字段”维护，不要改代码或脚本。
- 字典字段只表达通用字段、维度、指标原子字段；复杂口径仍维护为 Data Skills。
- 留存率、LTV、ARPU、付费金额差分、成熟 cohort 这类多步指标，不建议只靠一个字典字段表达，应写 Data Skill。
- 不同工作空间/数据源维护自己的字典，不要把某个项目的事件名、产品 ID、业务口径写成全局规则。
- 字段缺失时不要用相似字段替代；应补字典字段或补 Data Skill。
- 字典字段删除前先确认没有正在使用的图表配置依赖它；删除后不会自动替换为其他字段。
