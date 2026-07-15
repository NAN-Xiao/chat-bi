# 通用埋点 Excel 模板设计

## 目标

通用埋点模板用于把业务侧维护的事件、事件属性、公共属性、用户属性和 JSON 子字段统一导入工作空间数据字典。模板必须面向任意行业和数据源，不绑定游戏、卡牌、SLG、flam 或某个竞品系统。

模板导入后应服务同一份语义配置：

- LLM SQL：读取事件名、字段角色、字段说明、JSON 路径、表达式、示例值和 AI 注意事项。
- 图表配置器：读取字段展示名、字段类型、来源字段、JSON 路径和 SQL 表达式。
- 运维维护：支持 Excel 批量导入导出，也支持数据字典页面逐字段维护。

当前平台数据字典页面提供完整闭环：

- 下载模板：按当前绑定数据源的物理 schema 生成业务 sheet。
- 导出当前配置：把已有工作空间语义配置导出成同一套 Excel 结构。
- 导入配置：解析 Excel 后合并到 `tracking_config`，再由 LLM SQL 和图表配置器共同读取。

导入是按 `table_name`、`table_name + field_name`、`event_name` 合并，不会因为一个局部 Excel 缺少其它字段就清空已有配置。

## Sheet 组织原则

Excel 中的业务 sheet 应对应左侧数据字典里的真实物理表。例如一个项目可以有 `event`、`user` 两个业务 sheet，但不能把 `ext`、`personal`、`deviceinfo`、`adinfo` 这类 JSON 容器拆成物理表 sheet。普通 JSON 子字段统一维护在固定的 `JSON字段解析` Sheet。

模板可以包含两类 sheet：

- 系统 sheet：包括以下划线开头的 `_说明`、`_表映射`、`_枚举与值域`、`_SQL规则`，以及固定的 `事件参数对照`、`事件分组`、`JSON字段解析`。
- 业务表 sheet：sheet 名就是实际表名或映射到实际表名，例如 `event`、`user`、`fact_orders`。

JSON 嵌套结构仍属于某张真实表的字段元数据，不属于左侧表列表。比如 `event.ext.ed_ccu` 的层级是：

- 左侧表：`event`
- 表内 JSON 视图：`ext`
- 字典字段：`ext.ed_ccu`
- 来源字段：`ext`
- JSON 路径：`$.ed_ccu`

如果物理字段本身叫 `event` 且里面存 JSON 字符串，也按同样方式配置：

- 左侧表：`event`
- 表内 JSON 视图：`event`
- 字典字段：`event.xxx`
- 来源字段：`event`
- JSON 路径：`$.xxx`

### 1. `_说明`

面向运维和业务人员，说明字段命名、类型、来源字段、JSON 路径、表达式和导入规则。该 sheet 不参与导入。

### 2. `_表映射`

用于把埋点模板和实际物理表绑定。

| 列名 | 必填 | 说明 |
| --- | --- | --- |
| sheet_name | 否 | Excel sheet 名；为空时默认等于 `table_name` |
| table_name | 是 | 物理表名，例如 `event`、`user`、`fact_events` |
| table_display_name | 否 | 展示名 |
| table_role | 否 | 表角色，例如 `event_fact`、`daily_user_snapshot`、`dimension` |
| subject_field | 否 | 主体字段，例如 `uid`、`user_id` |
| event_name_field | 否 | 事件名字段 |
| event_time_field | 否 | 事件时间字段 |
| partition_field | 否 | 分区或业务日期字段 |
| table_comment | 否 | 表说明 |
| ai_notes | 否 | SQL 生成注意事项 |

### 3. `JSON字段解析`

固定维护普通 JSON 字典字段。该 Sheet 不加入 `_表映射`，也不会被识别成物理表。

| 列名 | 必填 | 说明 |
| --- | --- | --- |
| 来源表 | 否 | JSON 来源字段所在物理表；显式填写时必须存在且包含来源字段 |
| 来源字段 | 是 | 承载 JSON 文本的物理字段，例如 `userinfo`、`payload` |
| JSON路径 | 是 | 规范 JSON 路径，例如 `$._appVersion`、`$.items[0].sku` |
| 生成字段名 | 是 | 可查询字段名，必须与来源字段和路径一致，例如 `userinfo._appVersion` |
| 类型 | 是 | 文本、数值、布尔、时间、数组、对象或空值 |
| 属性说明 | 否 | 字段业务说明，进入字段注释和语义上下文 |

显式填写来源表时，导入器严格校验该表存在于当前绑定数据源的物理 schema，且该表确实包含来源字段；校验通过后直接使用该表，不再应用默认事件表优先规则。旧五列工作簿或来源表为空时，继续根据物理 schema 查找来源字段所在表：来源字段同时存在于多张表时优先默认事件表；没有默认事件表候选且无法唯一确定时导入失败。JSON 路径或生成字段名为空的确认行会返回警告并跳过，不生成 SQL 字段。

该 Sheet 中的有效字段会保存为 `tracking_config.fields` 的 `table_name/source_field/json_path/semantic_type` 元数据。SQL 表达式在运行时按当前 MySQL、PostgreSQL 或 ClickHouse 方言编译，Excel 不保存方言相关表达式。

平台导出时，`来源表`是 `JSON字段解析` 的可见第一列；event/user 中同名来源字段按表分别输出，不跨表去重。`event/user` 属性 Sheet 只保留物理字段和非 JSON 派生字段，普通 JSON 子字段只写入 `JSON字段解析`。事件专属属性继续由 `事件参数对照` 维护。通用表为保留既有字段枚举可以继续导出兼容的 `dictionary_field/field_value` 行；存在独立 Sheet 时，字段是否存在及其来源路径仍以 `JSON字段解析` 为准。

### 4. 业务表 sheet

每个真实表一个 sheet。sheet 内维护物理字段、非 JSON 派生字段，也可以维护事件定义和事件属性；普通 JSON 字段定义进入 `JSON字段解析`。

| 列名 | 必填 | 说明 |
| --- | --- | --- |
| row_type | 是 | 行类型：`physical_field`、`json_view`、`dictionary_field`、`event`、`event_property` |
| event_name | 否 | 事件名；`event` 和 `event_property` 行使用 |
| event_display_name | 否 | 事件展示名 |
| event_category | 否 | 事件分类 |
| field_view | 否 | 字段视图。JSON 子字段建议写成 `ext view`、`payload view`，导出时会按同一 view 合并单元格 |
| field_name | 是 | 物理字段名或逻辑字典字段名 |
| field_display_name | 否 | 字段展示名 |
| field_type | 是 | 平台类型：text、number、datetime、boolean、array、object、object_array、json |
| field_role | 否 | 字段角色：event_name、event_time、subject_id、json_path_dimension、json_path_metric 等 |
| semantic_type | 否 | 语义类型：identifier、category、number、date、timestamp、json 等 |
| source_field | 否 | 承载 JSON 的物理字段，例如 `ext`、`event`、`payload` |
| json_path | 否 | JSON 路径，例如 `$.pay_id`、`$.items[0].sku` |
| expression | 否 | 当前数据源方言 SQL 表达式 |
| required | 否 | 是否必填 |
| enum_values | 否 | 枚举值，逗号或换行分隔 |
| example_values | 否 | 示例值 |
| description | 否 | 字段或事件说明 |
| ai_notes | 否 | SQL/图表生成注意事项 |

行类型含义：

- `physical_field`：真实字段，例如 `uid`、`time`、`ext`、`event`。
- `json_view`：嵌套字段视图的父节点，本质上仍然指向某个物理 JSON 字符串字段。例如 `source_field=ext`、`field_name=ext`。
- `dictionary_field`：可供 LLM SQL 和图表配置器使用的逻辑字段或 JSON 子字段。Excel 中可以写 `field_view=ext view`、`field_name=ed_ccu`，导入后会还原为内部逻辑字段 `ext.ed_ccu`。
- `event`：事件名定义。
- `event_property`：某个事件下的属性定义。若属性来自 JSON，必须维护 `source_field` 和 `json_path`。

### 5. 兼容竞品格式的事件定义

| 列名 | 必填 | 说明 |
| --- | --- | --- |
| event_name | 是 | 事件名或埋点名 |
| event_display_name | 否 | 展示名 |
| event_description | 否 | 事件说明 |
| event_category | 否 | 分类标签，例如登录、支付、订单、生产、告警 |
| source_table | 否 | 所在物理表 |
| status | 否 | draft、active、deprecated |
| owner | 否 | 维护人 |
| ai_notes | 否 | 该事件的 SQL/分析注意事项 |

历史 Excel 中的“采集端”列仍可导入，但平台会忽略该列，后续导出不再包含它。

### 6. 兼容竞品格式的事件属性

描述某个事件下的属性或 JSON 子字段。适配竞品模板中的 `#事件数据` 右半部分。

| 列名 | 必填 | 说明 |
| --- | --- | --- |
| event_name | 是 | 所属事件；公共属性可留空并放到“公共事件属性” |
| property_name | 是 | 逻辑属性名，例如 `ext.pay_id`、`payload.amount` |
| property_display_name | 否 | 展示名 |
| property_type | 是 | 平台类型：text、number、datetime、boolean、array、object、object_array |
| field_role | 否 | 字段角色：event_name、event_time、subject_id、json_path_dimension、json_path_metric 等 |
| semantic_type | 否 | 语义类型：identifier、category、number、date、timestamp、json 等 |
| required | 否 | 是否必填 |
| source_table | 否 | 物理表 |
| source_field | 否 | 承载该属性的物理字段，例如 `ext`、`event`、`payload` |
| json_path | 否 | JSON 路径，例如 `$.pay_id`、`$.items[0].sku` |
| expression | 否 | 当前数据源方言 SQL 表达式 |
| enum_values | 否 | 枚举值，逗号或换行分隔 |
| example_values | 否 | 示例值 |
| description | 否 | 属性说明 |
| ai_notes | 否 | SQL/图表生成注意事项 |

### 7. 兼容竞品格式的公共事件属性

描述所有或多数事件都带的属性。适配竞品模板中的 `#公共事件属性`。

| 列名 | 必填 | 说明 |
| --- | --- | --- |
| property_name | 是 | 属性名 |
| property_display_name | 否 | 展示名 |
| property_type | 是 | 平台类型 |
| field_role | 否 | 字段角色 |
| semantic_type | 否 | 语义类型 |
| source_table | 否 | 物理表 |
| source_field | 否 | 物理字段 |
| json_path | 否 | JSON 路径 |
| expression | 否 | SQL 表达式 |
| description | 否 | 属性说明 |

### 8. 兼容竞品格式的用户属性

描述用户、账号、设备、组织、客户等主体属性。适配竞品模板中的 `#用户数据`，但不限定为游戏用户。

| 列名 | 必填 | 说明 |
| --- | --- | --- |
| subject_type | 否 | 主体类型，例如 user、account、device、customer、player |
| property_name | 是 | 属性名 |
| property_display_name | 否 | 展示名 |
| property_type | 是 | 平台类型 |
| update_mode | 否 | set、set_once、add、snapshot、derived |
| source_table | 否 | 物理表 |
| source_field | 否 | 物理字段 |
| json_path | 否 | JSON 路径 |
| expression | 否 | SQL 表达式 |
| property_category | 否 | 分类标签 |
| description | 否 | 属性说明 |
| ai_notes | 否 | SQL/分析注意事项 |

### 9. `_枚举与值域`

维护字段枚举、事件集合和维表引用。

| 列名 | 必填 | 说明 |
| --- | --- | --- |
| object_type | 是 | event、property、field、metric |
| object_name | 是 | 对象名 |
| value | 是 | 枚举值 |
| display_name | 否 | 枚举展示名 |
| description | 否 | 说明 |
| deprecated | 否 | 是否废弃 |

### 10. `_SQL规则`

维护轻量规则。复杂指标、跨表口径、漏斗、留存、LTV、成熟窗口等仍应进入 Data Skills，不建议塞进 Excel 字段说明里。

| 列名 | 必填 | 说明 |
| --- | --- | --- |
| rule_name | 是 | 规则名 |
| scope | 否 | 适用范围 |
| rule_text | 是 | 规则内容 |
| priority | 否 | 优先级 |

## 导入映射

- `_表映射` -> `tracking_config.tables` 与默认字段。
- `JSON字段解析` -> 带 `table_name/source_field/json_path` 的 `tracking_config.fields`；显式来源表优先，旧五列或空来源表的同名来源字段优先默认事件表。
- 业务表 sheet 的 `physical_field` / `json_view` / `dictionary_field` -> `tracking_config.fields`。
- 业务表 sheet 的 `event` / `event_property` -> `tracking_config.event_name_mappings` 与字段说明。
- `_枚举与值域` -> 字段 `value_mappings` 或事件集合映射。
- `_SQL规则` -> `tracking_config.sql_rules` 或 Data Skills。

## 兼容导入策略

平台内部应使用上述规范列名作为 canonical format。为了兼容竞品导入导出，可提供导入 profile：

- `shuzhi_generic_v1`：标准模板。
- `thinkingdata_like_v1`：兼容 `#事件数据`、`#公共事件属性`、`#用户数据` 这类表头。
- `custom_mapping`：用户上传列名映射后导入。

兼容 profile 只负责列名转换和类型归一，不应把任何行业事件名、指标口径或项目字段写入平台代码。

兼容 `thinkingdata_like_v1` 时，如果 Excel 没有显式 `source_table`，系统会优先使用当前工作空间的默认事件表或主体属性表；无法确定时应返回错误或警告，让运维补 `_表映射`，不能静默把事件属性塞进任意表。

## 类型归一

| 模板类型 | 平台类型 | 说明 |
| --- | --- | --- |
| 文本 / 字符串 / string | text | 标识符、枚举、描述 |
| 数值 / number | number | 可聚合指标 |
| 时间 / datetime / timestamp | datetime | 时间字段 |
| 布尔 / boolean | boolean | true/false |
| 列表 / array | array | 字符串数组 |
| 对象 / object | object | JSON object |
| 对象组 / object_array | object_array | JSON array of object |

## 运维原则

- 模板表达字段和事件，不表达复杂分析口径。
- 普通 JSON 子字段必须在 `JSON字段解析` 中维护来源表、来源字段、JSON 路径和生成字段名；事件专属属性维护在 `事件参数对照`。新版导出固定写出来源表，旧五列导入仍兼容。
- Excel 导出会用 `field_view` 合并单元格展示 JSON view；导入时 `field_view=ext view` 且 `field_name=foo` 会被识别为 `source_field=ext`、`json_path=$.foo`、内部字段名 `ext.foo`。
- JSON 字段表达式由平台按当前数据源方言运行时编译，不在 Excel 中维护 MySQL、PostgreSQL 或 ClickHouse 专用 SQL。
- 导入时遇到缺失来源字段、非法 JSON 路径、重复字段或不支持类型，应给出错误清单，不做静默替换。
- 同一工作空间内事件名应唯一；不同工作空间可以有同名事件但含义不同。
