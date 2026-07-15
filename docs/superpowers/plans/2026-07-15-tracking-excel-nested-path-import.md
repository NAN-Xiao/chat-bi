# 埋点 Excel 嵌套 JSON 路径导入修复 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复“事件参数对照”导入时显式来源字段下的嵌套 JSON 父路径被截断并发生属性碰撞的问题。

**Architecture:** 保持现有 Excel 契约和调用链，仅收紧 `_split_event_parameter_source(...)` 的来源前缀剥离条件。通过导入集成测试和导出再导入测试覆盖显式来源、自动推断和嵌套路径兼容性。

**Tech Stack:** Python 3、pytest、pandas、openpyxl、Pydantic DTO。

## Global Constraints

- 只修改 `backend/apps/system/crud/tracking_excel.py` 和 `backend/tests/test_tracking_excel.py`。
- 显式 `source_field` 优先；仅当属性名前缀与其相同，或来源字段为空时，才剥离来源前缀。
- 已显式提供的 `json_path` 继续优先于属性名推导。
- 不修改 Excel 表头、API、数据库结构、SQL 编译器或保存流程。
- 不实现 `[]` 数组元素、通配符或 unnest 语义。
- 保留当前工作区其他未提交修改，不纳入本修复。

---

### Task 1: 嵌套属性导入回归测试与最小修复

**Files:**
- Modify: `backend/tests/test_tracking_excel.py`
- Modify: `backend/apps/system/crud/tracking_excel.py:2238`

**Interfaces:**
- Consumes: `_split_event_parameter_source(source_field, property_name, json_path="")`。
- Produces: `(source_field, normalized_property_name, normalized_json_path)`，供 `_parse_event_parameter_mapping_sheet(...)` 生成事件属性配置。

- [ ] **Step 1: 编写显式来源字段嵌套路径失败测试**

在 `backend/tests/test_tracking_excel.py` 增加：

```python
def test_event_parameter_mapping_preserves_nested_paths_with_explicit_source() -> None:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "事件参数对照"
    sheet.append([
        "事件名（必填）", "事件显示名", "事件说明", "事件标签",
        "数据源字段", "属性名（必填）", "属性显示名", "属性类型（必填）", "属性说明",
    ])
    sheet.append(["ResourceChange", "资源变化", "", "资源", "personal", "ed_change.FOOD", "食物变化", "数值", ""])
    sheet.append(["", "", "", "", "personal", "ed_stock.FOOD", "食物存量", "数值", ""])
    output = BytesIO()
    workbook.save(output)

    parsed = parse_tracking_excel(
        output.getvalue(),
        TenantTrackingConfigDTO(tenant_id=2001, enabled=True),
        physical_schema={
            "event": PhysicalTableInfo(
                table_name="event",
                fields=[PhysicalFieldInfo("personal", "json", "事件属性")],
            )
        },
        datasource_type="mysql",
    )
    event = next(item for item in parsed.editor.event_name_mappings if item.get("event_name") == "ResourceChange")
    props = event["properties"]
    assert [(item["property_name"], item["json_path"]) for item in props] == [
        ("personal.ed_change.FOOD", "$.ed_change.FOOD"),
        ("personal.ed_stock.FOOD", "$.ed_stock.FOOD"),
    ]
```

- [ ] **Step 2: 运行测试确认 RED**

Run: `D:/AIWork3/chat-bi/backend/.venv/Scripts/python.exe -m pytest backend/tests/test_tracking_excel.py::test_event_parameter_mapping_preserves_nested_paths_with_explicit_source -q`

Expected: FAIL；当前结果将父路径截断为 `personal.FOOD / $.FOOD`，并可能合并为一条属性。

- [ ] **Step 3: 实现最小前缀判断**

把 `_split_event_parameter_source(...)` 中无条件截断改为：

```python
inferred_source, inferred_path = _json_path_from_field_name(name)
if inferred_source and (not source or inferred_source == source):
    source = source or inferred_source
    name = name.split(".", 1)[1]
```

后续显式路径和自动路径生成逻辑保持不变。

- [ ] **Step 4: 运行目标测试确认 GREEN**

Run: `D:/AIWork3/chat-bi/backend/.venv/Scripts/python.exe -m pytest backend/tests/test_tracking_excel.py::test_event_parameter_mapping_preserves_nested_paths_with_explicit_source -q`

Expected: PASS。

### Task 2: 导出往返兼容与完整验证

**Files:**
- Modify: `backend/tests/test_tracking_excel.py`
- Verify: `D:/AIWork3/djinchao/chat-bi/docs/xiuxian/tracking_dictionary_0715_json_expanded.xlsx`

**Interfaces:**
- Consumes: `tracking_config_excel(...)` 导出的“事件参数对照”工作簿。
- Produces: `parse_tracking_excel(...)` 可稳定恢复的嵌套事件属性。

- [ ] **Step 1: 编写嵌套属性导出再导入测试**

构造带 `source_field=ext`、`json_path=$.hero_info.hero_level` 的事件属性，先调用
`tracking_config_excel(...)`，再调用 `parse_tracking_excel(...)`，断言导入结果为：

```python
assert prop["property_name"] == "ext.hero_info.hero_level"
assert prop["source_field"] == "ext"
assert prop["json_path"] == "$.hero_info.hero_level"
```

- [ ] **Step 2: 运行往返测试确认通过**

Run: `D:/AIWork3/chat-bi/backend/.venv/Scripts/python.exe -m pytest backend/tests/test_tracking_excel.py -q`

Expected: 全部测试通过。

- [ ] **Step 3: 对实际 0715 文件做只读解析复验**

使用文件 `event`/`user` Sheet 构造 `PhysicalTableInfo`，调用 `parse_tracking_excel(...)`，断言：

```python
assert ("personal.ed_change.FOOD", "$.ed_change.FOOD") in resource_pairs
assert ("personal.ed_stock.FOOD", "$.ed_stock.FOOD") in resource_pairs
assert len(resource_properties) == 57
```

同时输出数组路径统计，并明确数组字段仍不属于本次修复。

- [ ] **Step 4: 检查差异和提交**

Run: `git diff --check -- backend/apps/system/crud/tracking_excel.py backend/tests/test_tracking_excel.py`

Expected: 无空白错误，仅包含前缀判断和对应测试。

提交：

```powershell
git add -- backend/apps/system/crud/tracking_excel.py backend/tests/test_tracking_excel.py
git commit -m "修复：保留埋点事件嵌套JSON路径"
```
