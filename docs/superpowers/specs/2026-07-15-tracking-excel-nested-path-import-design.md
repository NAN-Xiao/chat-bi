# 埋点 Excel 嵌套 JSON 路径导入修复设计

## 目标

修复“事件参数对照”导入时错误截断嵌套 JSON 父路径的问题。显式配置
`source_field=personal`、`property_name=ed_change.FOOD` 时，导入结果必须保留为
`property_name=personal.ed_change.FOOD`、`json_path=$.ed_change.FOOD`，不能降级为
`personal.FOOD`、`$.FOOD`。

## 根因

`_split_event_parameter_source(...)` 当前只要发现属性名包含点号，就无条件把第一段当作来源字段移除。
当来源字段已经明确为 `personal` 时，`ed_change` 实际是 `personal` 内部的对象键，不是来源字段，
因此该逻辑会丢失父路径，并使 `ed_change.FOOD` 与 `ed_stock.FOOD` 静默碰撞。

## 修复规则

1. 显式 `source_field` 为空时，继续允许从 `source.child` 属性名推断来源字段，并移除相同前缀。
2. 显式 `source_field` 非空且属性名首段与其相同时，移除重复的来源前缀。
3. 显式 `source_field` 非空且属性名首段与其不同时，首段属于 JSON 子路径，必须完整保留。
4. 未显式提供 `json_path` 时，从修正后的完整子属性名生成 JSONPath。
5. 已显式提供 `json_path` 时，以显式路径为准，现有行为保持不变。

## 兼容示例

| 来源字段 | 属性名 | 规范化属性名 | JSONPath |
| --- | --- | --- | --- |
| `personal` | `ed_change.FOOD` | `ed_change.FOOD` | `$.ed_change.FOOD` |
| `personal` | `personal.ed_change.FOOD` | `ed_change.FOOD` | `$.ed_change.FOOD` |
| 空 | `ext.hero_info.level` | `hero_info.level` | `$.hero_info.level` |
| `ext` | `battleResult` | `battleResult` | `$.battleResult` |

事件属性最终内部名称继续由调用方拼接为 `source_field.property_name`。

## 修改范围

- 修改 `backend/apps/system/crud/tracking_excel.py` 的 `_split_event_parameter_source(...)`。
- 在 `backend/tests/test_tracking_excel.py` 增加嵌套事件属性导入和导出后再导入的回归测试。
- 不修改工作簿格式、API、数据库结构、运行时 JSON SQL 编译逻辑或其他导入 Sheet。

## 测试与验收

- 先添加失败测试，证明 `personal + ed_change.FOOD` 当前错误得到 `$.FOOD`。
- 验证 `ed_change.FOOD` 与 `ed_stock.FOOD` 导入后是两个不同属性和 JSONPath。
- 验证 `ext.hero_info.hero_level` 导出后再导入仍得到 `$.hero_info.hero_level`。
- 运行完整 `backend/tests/test_tracking_excel.py`。
- 使用 `tracking_dictionary_0715_json_expanded.xlsx` 做只读解析，确认 `ResourceChange` 的
  `ed_change.*` 与 `ed_stock.*` 不再碰撞。

## 明确不包含

本次不实现 `[]` 数组元素、通配符或 unnest 语义。带 `[]` 的事件属性仍需后续独立设计；
完成本修复后，当前 0715 扩展文件仍不能因数组字段而被视为整体可安全导入。
