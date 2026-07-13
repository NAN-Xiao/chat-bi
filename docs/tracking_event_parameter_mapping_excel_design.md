# 数据字典事件参数对照 Excel 开发文档

## 背景

数据字典页面当前提供「下载模板」「导出当前配置」「导入配置」三个 Excel 操作入口。前端入口位于 `frontend/src/views/system/data-dictionary/DataDictionary.vue`，后端接口位于 `backend/apps/system/api/tracking_config.py`，实际 Excel 解析与生成逻辑集中在 `backend/apps/system/crud/tracking_excel.py`。

当前 Excel 以物理表 sheet 为主要维护入口，在事件明细表 sheet 中混合输出物理字段、JSON 字典字段、字段枚举值、事件名取值和事件属性关系。这个结构对平台内部配置较完整，但业务人员维护「事件名 event 与事件参数 ext 的对照关系」时不够直观。

本次目标是在不改变前端按钮入口的前提下，新增一个固定 sheet「事件参数对照」，专门维护事件与 ext 参数的关系，并把 `event` 表、`user` 表的字段导入导出版式调整为业务配置人员更容易维护的「属性表」格式。

## 目标

1. Excel 导出新增固定 sheet：`事件参数对照`。
2. `事件参数对照` 中每一行表达一个事件定义或一个事件参数关系。
3. 属性名导出为短名，例如 `battleResult`，不导出为 `ext.battleResult`。
4. 新增「数据源字段」列，用于表达该参数来自哪个 JSON 容器字段，例如 `ext`。
5. 导入 `事件参数对照` 后，能够恢复到现有 `event_name_mappings[].properties` 配置结构。
6. 事件明细物理表 sheet 不再输出事件相关内容，包括 `event_value` 行和从 `event_name_mappings[].properties` 展开的事件属性行。
7. 继续兼容历史 Excel 格式导入，避免已有导出文件无法导入。
8. `event` 表和 `user` 表的导入导出参照属性维护表格式：`属性名（必填）`、`属性显示名`、`属性类型（必填）`、`更新方式`、`属性说明`、`属性标签`。
9. 「更新方式」需要结构化保存，保证导入后再次导出不丢失。

## 非目标

1. 不新增前端按钮，不改变现有三个入口的交互路径。
2. 不把 SLG 或游戏领域口径写入平台通用逻辑。
3. 不移除普通字典字段、物理字段、普通字段枚举值的导入导出能力。
4. 不改变图 2 页面列表的数据展示模型；导入成功后仍按当前逻辑刷新 schema。
5. 不创建聚合指标表、快照表或领域专用分析层。

## 当前代码逻辑

### 前端入口

文件：`frontend/src/views/system/data-dictionary/DataDictionary.vue`

关键函数：

- `downloadTrackingTemplate()` 调用 `trackingConfigApi.downloadTemplate()`。
- `exportTrackingConfig()` 调用 `trackingConfigApi.exportExcel()`。
- `importTrackingExcel()` 调用 `trackingConfigApi.importExcel(file)`。
- 导入成功后更新 `trackingConfig.value`，再调用 `loadSchema(...)` 或 `loadDatasources()` 刷新字段列表。

API 定义在 `frontend/src/api/system.ts`：

- `GET /system/tracking-config/template`
- `GET /system/tracking-config/export`
- `POST /system/tracking-config/importExcel`

### 后端接口

文件：`backend/apps/system/api/tracking_config.py`

关键流程：

1. `_workspace_physical_schema(...)` 读取当前工作空间绑定数据源的物理表与字段。
2. `download_tracking_config_template(...)` 调用 `tracking_config_excel(..., template_only=True)`。
3. `export_current_tracking_config(...)` 调用 `tracking_config_excel(..., template_only=False)`。
4. `import_tracking_config_excel(...)` 读取上传文件后调用 `parse_tracking_excel(...)`。
5. 解析结果通过 `save_tracking_config(...)` 保存到当前租户和当前数据源绑定下。

### Excel 核心逻辑

文件：`backend/apps/system/crud/tracking_excel.py`

关键函数：

- `tracking_config_excel(...)` 负责导出模板或当前配置。
- `parse_tracking_excel(...)` 负责解析 Excel。
- `_parse_generic_business_sheet(...)` 负责解析物理表 sheet。
- `_business_event_value_rows(...)` 将 `event_name_mappings` 导出为 `event_value` 行。
- `_business_event_property_rows(...)` 将 `event_name_mappings[].properties` 导出为事件属性 `dictionary_field` 行。
- `_append_event_mapping(...)` 将事件定义和属性关系合并进 `event_name_mappings`。

现有结构已经支持事件属性关系，因此新增 sheet 只需要做 Excel 层适配，不需要新存储模型。

补充约束：现有 `TenantTrackingFieldBase` 和 `TenantTrackingFieldModel` 没有 `update_mode` 字段。若 `event/user` 表需要稳定支持「更新方式」导入导出，后续实现必须增加字段级结构化存储。推荐优先增加通用扩展字段 `metadata` 或明确字段 `update_mode`，不要把更新方式拼进 `field_comment` 或 `ai_notes`，否则会造成再次导出、校验和后续 AI 使用都不稳定。

## 新增 Sheet 设计

固定 sheet 名称：`事件参数对照`

建议列顺序：

| 列名 | 必填 | 说明 |
| --- | --- | --- |
| 事件名 | 是 | 上报事件名，例如 `battle_end`。 |
| 事件显示名 | 否 | 事件中文名，例如 `战斗结束`。 |
| 事件说明 | 否 | 事件用途、触发时机或业务说明。 |
| 事件标签 | 否 | 事件分类或业务标签，例如 `战斗`、`任务与活动`。 |
| 数据源字段 | 否 | 参数所在 JSON 容器字段，默认可推断为 `ext`。 |
| 属性名 | 否 | 参数短名，例如 `battleResult`。事件无参数时可为空。 |
| 属性显示名 | 否 | 参数中文名，例如 `战斗结果`。 |
| 属性类型 | 否 | 参数类型，例如 `文本`、`数值`、`布尔`、`对象组`。 |
| 属性说明 | 否 | 参数业务含义、单位、枚举说明或取值示例。 |

### 导出规则

1. 每个事件至少导出一行。
2. 如果事件存在 `properties`，每个属性导出一行。
3. 如果事件没有 `properties`，导出一行事件定义，属性相关列为空。
4. `property_name` 导出时去掉数据源字段前缀：
   - 内部为 `ext.battleResult`，导出「数据源字段」=`ext`，「属性名」=`battleResult`。
   - 内部为 `battleResult` 且有 `source_field=ext`，导出「数据源字段」=`ext`，「属性名」=`battleResult`。
5. `json_path=$.battleResult` 时，属性名优先取 JSON 路径末段 `battleResult`。
6. `event_category` 导出到「事件标签」。
7. `event_display_name` 导出到「事件显示名」。
8. `description` 或 `event_description` 导出到「事件说明」。
9. `property_type` 导出到「属性类型」，如果为空则用 `semantic_type` 或 `field_type` 兜底。

### 导入规则

1. `parse_tracking_excel(...)` 识别到 `事件参数对照` sheet 后，单独调用新解析函数。
2. 每行必须有「事件名」，否则跳过并记录 warning。
3. 「事件名」相同的多行合并到同一个 `event_name_mappings` 项。
4. 事件基础信息按非空值合并：
   - `event_name`
   - `event_display_name`
   - `event_category`
   - `description`
5. 如果「属性名」为空，只维护事件定义，不创建属性。
6. 如果「数据源字段」为空，默认使用 `ext`。
7. 如果「属性名」包含点号，例如 `ext.battleResult`：
   - 点号前缀作为 `source_field`
   - 点号后半段作为短属性名
   - `json_path=$.battleResult`
8. 如果「属性名」不含点号，例如 `battleResult`：
   - `source_field` 使用「数据源字段」
   - `json_path=$.battleResult`
   - 内部 `property_name` 建议保存为 `ext.battleResult`
9. 属性信息写入当前事件的 `properties`：
   - `property_name`
   - `property_display_name`
   - `property_type`
   - `source_field`
   - `json_path`
   - `description`
10. 导入时应把 `事件参数对照` 中的事件关系视为当前 Excel 的权威事件配置；同名事件下同名属性以后导入值为准。

## 物理表 Sheet 调整

### event/user 表新版式

`event` 表和 `user` 表导入导出统一采用属性维护表格式。sheet 名仍使用物理表名或 `_表映射` 中映射出来的 sheet 名，不新增 `event字段`、`user字段` 等额外 sheet。

建议列顺序：

| 列名 | 必填 | 说明 |
| --- | --- | --- |
| 属性名（必填） | 是 | 字段名或 JSON 子字段名，例如 `account_id`、`bag_info.item_id`、`hero_detail.hero_level`。 |
| 属性显示名 | 否 | 中文显示名，例如 `账号ID`、`道具ID`。 |
| 属性类型（必填） | 是 | 字段类型，例如 `文本`、`数值`、`时间`、`布尔`、`对象组`。 |
| 更新方式 | 否 | 字段更新策略，例如 `user_setOnce`、`user_set`、`user_add`；事件表没有稳定更新策略时可为空。 |
| 属性说明 | 否 | 字段说明、单位、格式、取值样例或更新说明。 |
| 属性标签 | 否 | 字段分类标签，例如 `基础属性`、`背包`、`战斗`。 |

导出规则：

1. `event` 表和 `user` 表不再导出 `row_type`、`field_name`、`field_role`、`semantic_type`、`source_field`、`json_path` 等内部维护列。
2. `field_name` 导出为「属性名（必填）」。
3. `aliases` 的第一个值或字段显示名导出为「属性显示名」。
4. `semantic_type` 或物理字段类型转换为「属性类型（必填）」。
5. `update_mode` 导出为「更新方式」。
6. `field_comment` 或字段原始备注导出为「属性说明」。
7. 字段分类导出为「属性标签」。后续实现可优先读取字段 metadata 中的 `category`，没有时为空。
8. JSON 子字段导出为点号短路径，例如 `bag_info.item_id`、`hero_detail.hero_level`；导入时再推断 `source_field=bag_info`、`json_path=$.item_id`。

导入规则：

1. 识别到 sheet 表头包含「属性名（必填）」和「属性类型（必填）」时，按新版属性表格式解析。
2. 「属性名（必填）」为空的行跳过并记录 warning。
3. 「属性类型（必填）」为空的行跳过并记录 warning。
4. 属性名包含点号时，按 JSON 子字段处理：
   - `bag_info.item_id` -> `source_field=bag_info`、`json_path=$.item_id`
   - `hero_detail.hero_level` -> `source_field=hero_detail`、`json_path=$.hero_level`
5. 属性名不含点号时，按物理字段或普通字典字段处理。
6. 「属性显示名」写入 `aliases` 的首个别名。
7. 「属性类型（必填）」写入 `semantic_type`，并沿用现有 `_semantic_type(...)` 类型规范化。
8. 「更新方式」写入结构化字段 `update_mode`。
9. 「属性说明」写入 `field_comment`。
10. 「属性标签」写入字段 metadata 的 `category`，不要写死成业务领域逻辑。

### 其他物理表兼容格式

导出时，非 `event/user` 的其他物理表 sheet 可继续使用当前通用格式：

1. 物理字段 `physical_field`。
2. 普通 JSON 字典字段 `dictionary_field`。
3. 普通字段枚举 `field_value`。

导出时，事件明细物理表 sheet 额外不再输出：

1. `_business_event_value_rows(...)` 生成的 `event_value` 行。
2. `_business_event_property_rows(...)` 生成的事件属性行。

这意味着 `tracking_config_excel(...)` 中当前这段事件表特殊插入逻辑需要调整：

- 不再把 `event_value_rows` 和 `event_property_rows` 插入事件表 sheet。
- 改为在所有物理表 sheet 之后、`_SQL规则` 之前或之后插入 `事件参数对照` sheet。

推荐位置：`_表映射` 之后、各物理表 sheet 之前。这样业务维护者打开 Excel 后更容易先看到事件与参数关系。

## 表头兼容

需要在 `HEADER_ALIASES` 中补充中文列名映射：

| 中文表头 | 内部字段 |
| --- | --- |
| 事件标签 | `event_category` |
| 事件名 | `event_name` |
| 事件显示名 | `event_display_name` |
| 事件说明 | `event_description` |
| 数据源字段 | `source_field` |
| 属性名 | `property_name` |
| 属性显示名 | `property_display_name` |
| 属性类型 | `property_type` |
| 属性说明 | `description` |
| 属性名 | `property_name` 或 `field_name`，在 `事件参数对照` 中表示 `property_name`，在 `event/user` 表中表示 `field_name` |
| 属性名必填 | `field_name` |
| 属性显示名 | `field_display_name` |
| 属性类型必填 | `field_type` |
| 更新方式 | `update_mode` |
| 属性标签 | `field_category` |

需要新增专用列常量：

- `EVENT_PARAMETER_MAPPING_SHEET = "事件参数对照"`
- `EVENT_PARAMETER_MAPPING_COLUMNS = [...]`
- `EVENT_PARAMETER_MAPPING_EXPORT_LABELS = {...}` 或复用 `EXPORT_COLUMN_LABELS`
- `ATTRIBUTE_SHEET_COLUMNS = ["field_name", "field_display_name", "field_type", "update_mode", "description", "field_category"]`

## 兼容策略

1. 历史物理表 sheet 中的 `event_value` 仍继续支持导入。
2. 历史物理表 sheet 中带 `event_name` 的 `dictionary_field` 仍继续支持导入为事件属性。
3. 新格式和旧格式同时存在时，建议以 `事件参数对照` 为准，旧格式解析后可被新 sheet 同名事件/同名属性覆盖。
4. 导出只输出新格式事件关系，避免用户继续维护旧事件行。
5. `event/user` 表导入时同时支持新版属性表格式和历史通用格式。判断依据是表头：存在「属性名（必填）」和「属性类型（必填）」时走新版属性表解析，否则走 `_parse_generic_business_sheet(...)`。
6. 历史 Excel 中的“采集端”列仍可导入，但平台会忽略该列，后续导出不再包含它。

## 建议新增函数

文件：`backend/apps/system/crud/tracking_excel.py`

### `_event_parameter_mapping_rows(config)`

职责：从 `TenantTrackingConfigDTO.event_name_mappings` 生成 `事件参数对照` sheet 行。

输入：

- `config: TenantTrackingConfigDTO`

输出：

- `list[dict[str, Any]]`

核心处理：

- 遍历 `config.event_name_mappings`
- 展开事件名
- 展开 `properties`
- 规范化 `source_field` 和短属性名

### `_parse_event_parameter_mapping_sheet(rows, editor, warnings)`

职责：解析 `事件参数对照` sheet 并写入 `editor.event_name_mappings`。

输入：

- `rows: list[dict[str, Any]]`
- `editor: TenantTrackingConfigEditor`
- `warnings: list[str]`

输出：

- 无返回值，直接更新 `editor`

核心处理：

- 缺少事件名的行记录 warning
- 合并同名事件
- 属性名为空时只保存事件定义
- 属性名不为空时写入 `properties`

### `_split_property_source(source_field, property_name, json_path)`

职责：把导入或导出的属性来源规范化。

输入：

- `source_field: str`
- `property_name: str`
- `json_path: str`

输出：

- `(source_field, short_property_name, normalized_json_path, internal_property_name)`

规则：

- `source_field` 为空时默认 `ext`
- `property_name=ext.battleResult` 时短名为 `battleResult`
- `property_name=battleResult` 时内部名为 `ext.battleResult`
- `json_path` 统一为 `$.battleResult`

### `_attribute_sheet_rows(table_name, fields, physical_fields)`

职责：把 `event/user` 表字段导出为属性维护表格式。

输入：

- `table_name: str`
- `fields: list[TenantTrackingFieldBase]`
- `physical_fields: list[PhysicalFieldInfo]`

输出：

- `list[dict[str, Any]]`

核心处理：

- 物理字段和已配置字段合并。
- 字段名导出到 `field_name`。
- 第一个别名导出到 `field_display_name`。
- 语义类型导出到 `field_type`。
- 结构化 `update_mode` 导出到 `update_mode`。
- 字段说明导出到 `description`。
- 字段 metadata 中的 `category` 导出到 `field_category`。

### `_parse_attribute_sheet(rows, table_name, editor, warnings)`

职责：解析 `event/user` 表属性维护格式。

输入：

- `rows: list[dict[str, Any]]`
- `table_name: str`
- `editor: TenantTrackingConfigEditor`
- `warnings: list[str]`

输出：

- 无返回值，直接更新 `editor.fields`

核心处理：

- 校验 `field_name` 和 `field_type`。
- 推断 JSON 子字段来源。
- 保存 `field_comment`、`semantic_type`、`aliases`、`update_mode` 和字段分类 metadata。
- 对同一 `table_name + field_name` 去重，后出现的有效行覆盖前一行。

## 测试计划

测试文件：`backend/tests/test_tracking_excel.py`

### 用例一：导出新增事件参数对照 sheet

验证点：

1. workbook 包含 `事件参数对照`。
2. `事件参数对照` 表头包含「数据源字段」和「属性名」。
3. `login` 事件的 `duration` 参数导出为：
   - 数据源字段：`event_props` 或配置中的 JSON 容器字段
   - 属性名：`duration`
4. 属性名不带 `event_props.` 前缀。

### 用例二：事件表 sheet 不再输出事件相关行

验证点：

1. `event_log` sheet 不包含 `event_value` 行。
2. `event_log` sheet 不包含由 `event_name_mappings[].properties` 展开的事件属性行。
3. 普通字典字段和普通字段枚举仍保留。

### 用例三：新 sheet 可导入为事件属性关系

构造 Excel：

- sheet 名：`事件参数对照`
- 行内容：
  - 事件名：`battle_end`
  - 事件显示名：`战斗结束`
  - 事件标签：`战斗`
  - 数据源字段：`ext`
  - 属性名：`battleResult`
  - 属性显示名：`战斗结果`
  - 属性类型：`文本`
  - 属性说明：`战斗结果字段`

验证导入结果：

- 存在 `event_name_mappings[].event_name == "battle_end"`。
- 该事件存在 `properties[]`。
- 属性满足：
  - `property_name == "ext.battleResult"`
  - `property_display_name == "战斗结果"`
  - `property_type == "文本"`
  - `source_field == "ext"`
  - `json_path == "$.battleResult"`

### 用例四：属性名包含数据源字段时可兼容

输入：

- 数据源字段：空
- 属性名：`ext.battleResult`

验证：

- `source_field == "ext"`
- `json_path == "$.battleResult"`
- 导出时仍显示属性名 `battleResult`

### 用例五：旧格式仍可导入

复用现有测试：

- `test_event_sheet_event_value_rows_can_roundtrip_event_dictionary`
- `test_compact_event_value_rows_inherit_previous_context`

根据新导出行为调整测试构造方式，确保旧格式手工 Excel 仍可解析。

### 用例六：event/user 表导出为属性维护格式

验证点：

1. `event` 或 `event_log` sheet 表头为「属性名（必填）」「属性显示名」「属性类型（必填）」「更新方式」「属性说明」「属性标签」。
2. sheet 中不出现 `row_type` 表头。
3. JSON 子字段导出为 `hero_detail.hero_level` 这种点号路径。
4. 字段说明保留原字段说明。

### 用例七：user 表属性维护格式可导入更新方式

构造 Excel：

- sheet 名：`user`
- 表头：`属性名（必填）`、`属性显示名`、`属性类型（必填）`、`更新方式`、`属性说明`、`属性标签`
- 行内容：
  - 属性名：`total_revenue`
  - 属性显示名：`累计付费金额`
  - 属性类型：`数值`
  - 更新方式：`user_add`
  - 属性说明：`累计付费金额，每次充值成功时累加`
  - 属性标签：`付费`

验证导入结果：

- 存在 `table_name == "user"` 且 `field_name == "total_revenue"` 的字段配置。
- `semantic_type == "number"`。
- `aliases` 包含 `累计付费金额`。
- `update_mode == "user_add"`。
- 字段 metadata 中 `category == "付费"`。

## 风险与处理

### 风险一：同一个事件参数也存在普通字段配置

处理：`事件参数对照` 只维护事件下的 `properties` 关系，不删除普通 `fields` 中的同名 JSON 字典字段。这样图 2 字段列表仍可展示字段，事件关系也能供 AI prompt 使用。

### 风险二：数据源字段不一定叫 ext

处理：新增「数据源字段」列。导出按已有 `source_field` 输出；导入为空时才默认 `ext`。

### 风险三：历史 Excel 中事件信息仍在物理表 sheet

处理：继续保留 `_parse_generic_business_sheet(...)` 的旧格式解析逻辑。导出不再产生旧格式，导入仍兼容旧格式。

### 风险四：事件无参数时导入后丢事件

处理：允许「属性名」为空的事件定义行。解析时只创建事件，不创建 property。

### 风险五：更新方式没有现成存储字段

处理：后续实现必须补充字段级结构化存储。推荐方案是新增 `TenantTrackingFieldBase.update_mode` 和 `TenantTrackingFieldModel.update_mode`；如果希望减少列变更，也可以新增通用 JSON metadata 字段，但不能把更新方式混入说明文本。

## 验收标准

1. 点击「导出当前配置」后，Excel 包含固定 sheet `事件参数对照`。
2. `事件参数对照` 中属性名显示为 `battleResult`，并通过「数据源字段」列显示 `ext`。
3. 事件明细表 sheet 不再出现 `event_value` 行。
4. 事件明细表 sheet 不再出现从事件属性关系展开的事件参数行。
5. 导入 `事件参数对照` 后，图 2 中事件名和值字典仍可正常展示。
6. Smart Q&A、分析助手等依赖 `event_name_mappings` 的能力仍能读取事件与参数关系。
7. 现有历史格式 Excel 仍可导入，不出现阻断性错误。
8. `event/user` 表导出为属性维护格式，不再暴露 `row_type` 等内部列。
9. `user` 表导入「更新方式」后再次导出仍能保留相同值。

## 推荐实施顺序

1. 在 `tracking_excel.py` 中新增 sheet 常量、列常量和表头映射。
2. 先写导出测试，锁定 `事件参数对照` 的表头和行数据。
3. 实现 `_event_parameter_mapping_rows(...)`。
4. 调整 `tracking_config_excel(...)`，插入新 sheet，并移除事件表中的事件相关输出。
5. 写导入测试，覆盖短属性名、带前缀属性名、事件无参数三种情况。
6. 实现 `_parse_event_parameter_mapping_sheet(...)` 和属性来源规范化函数。
7. 补充 `event/user` 表属性维护格式导出测试。
8. 实现 `_attribute_sheet_rows(...)`，让 `event/user` 表导出为新版属性表。
9. 补充 `event/user` 表属性维护格式导入测试，重点覆盖 `update_mode` 和 JSON 子字段。
10. 实现 `_parse_attribute_sheet(...)` 和字段级 `update_mode` 持久化。
11. 回归现有 `backend/tests/test_tracking_excel.py`。
12. 手动从页面导出一次 Excel，检查 sheet 顺序、表头、属性名、数据源字段和更新方式是否符合预期。
