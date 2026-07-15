# JSON 子字段显示名称闭环 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 `JSON字段解析` 显式维护并往返保留字段显示名，同时让数据字典和图表字段选择器在未配置显示名时分别回退到完整字段名和叶子属性名。

**Architecture:** 继续使用 `TenantTrackingField.aliases[0]` 作为主显示名，不新增数据库字段。Excel 导入导出负责显式显示名的配置闭环；datasource 字段列表接口只对 JSON 派生字段禁止说明回退；前端把字段名称选择抽成纯函数，使下拉行和已选值使用同一规则。

**Tech Stack:** Python 3.11、FastAPI/SQLModel、pytest、pandas/openpyxl/xlsxwriter、Vue 3、TypeScript、Node.js 原生断言测试。

## Global Constraints

- `JSON字段解析` 新表头固定为：`来源表`、`来源字段`、`JSON路径`、`生成字段名`、`字段显示名`、`类型`、`属性说明`。
- 旧五列和六列工作簿必须继续兼容；缺少字段显示名时按空值处理。
- 字段显示名只来自显式配置，不从属性说明猜测、截取或自动生成。
- 数据字典无显示名时展示完整规范字段名，例如 `adinfo.adId`。
- 图表字段选择器无显示名时展示叶子属性名，例如 `adId`。
- 普通物理字段继续保留现有字段说明回退，避免 `dt` 等已有友好名称回归。
- 不修改数据库模型、数据库迁移、SQL 方言编译器、事件参数配置和数据字典页面布局。
- 所有代码注释、测试说明和 Git 提交信息使用中文。
- 每个行为变更必须先写失败测试并确认失败原因，再写生产代码。

---

## File Map

- `backend/apps/system/crud/tracking_excel.py`：定义 `JSON字段解析` 表头、导入合并和导出行。
- `backend/tests/test_tracking_excel.py`：验证七列表头、显示名导入导出和旧格式兼容。
- `docs/generic_tracking_excel_template.md`：记录用户可见的固定列契约。
- `backend/apps/datasource/api/datasource.py`：区分物理字段与 JSON 派生字段的 `display_name` 回退。
- `backend/tests/test_datasource_field_list_items.py`：验证别名、说明和 JSON 字段列表输出语义。
- `frontend/src/views/dashboard/common/builderFieldPickerOptions.ts`：提供可复用、可单测的字段名称选择函数。
- `frontend/src/views/dashboard/common/builderFieldPickerOptions.test.mjs`：验证 JSON 叶子名和普通字段名称规则。
- `frontend/src/views/dashboard/common/BuilderFieldPicker.vue`：让下拉行和已选值统一调用名称函数。
- `frontend/src/views/system/data-dictionary/DataDictionary.vue`：不修改；现有 `display_name || field_name` 已符合设计。

---

### Task 1: `JSON字段解析` 显示名导入导出闭环

**Files:**
- Modify: `backend/tests/test_tracking_excel.py:93-220,1620-1810`
- Modify: `backend/apps/system/crud/tracking_excel.py:128-170,1592-1630,2698-2724`
- Modify: `docs/generic_tracking_excel_template.md:67-84`

**Interfaces:**
- Consumes: `TenantTrackingFieldBase.aliases: list[str]`、`_field_item(...)`、`_first_alias(...)`。
- Produces: `JSON_FIELD_PARSING_COLUMNS` 七列契约；导入行的 `field_display_name -> aliases[0]`；导出行的 `aliases[0] -> field_display_name`。

- [ ] **Step 1: 把测试表头扩展为七列，并保留显式旧格式常量**

在 `backend/tests/test_tracking_excel.py` 将测试常量调整为：

```python
JSON_FIELD_PARSING_HEADERS = [
    "来源表",
    "来源字段",
    "JSON路径",
    "生成字段名",
    "字段显示名",
    "类型",
    "属性说明",
]
SOURCE_TABLE_JSON_FIELD_PARSING_HEADERS = [
    "来源表",
    "来源字段",
    "JSON路径",
    "生成字段名",
    "类型",
    "属性说明",
]
LEGACY_JSON_FIELD_PARSING_HEADERS = SOURCE_TABLE_JSON_FIELD_PARSING_HEADERS[1:]
```

把使用新版默认表头的测试数据行补上“字段显示名”单元格。需要表达业务名称的行填写名称；只验证技术字段的行填写空字符串。

- [ ] **Step 2: 写显示名导入和往返失败测试**

扩展 `test_json_field_parsing_sheet_imports_fields_and_prefers_event_table`：

```python
parsed = parse_tracking_excel(
    _json_overview_workbook(
        [["", "userinfo", "$._appVersion", "userinfo._appVersion", "应用版本", "文本", "客户端应用版本"]]
    ),
    TenantTrackingConfigDTO(tenant_id=2001, enabled=True, default_event_table="event"),
    physical_schema=_json_overview_physical_schema(),
    datasource_type="mysql",
)

field = next(item for item in parsed.editor.fields if item.field_name == "userinfo._appVersion")
assert field.aliases == ["应用版本"]
assert field.field_comment == "客户端应用版本"
```

扩展 `test_template_exports_json_dictionary_fields_only_in_json_overview`，给一个字段配置主别名并验证导出、再导入：

```python
field = TenantTrackingFieldDTO(
    tenant_id=2001,
    table_name="event",
    field_name="adinfo.adsetId",
    field_comment="广告组标识说明",
    semantic_type="text",
    source_field="adinfo",
    json_path="$.adsetId",
    aliases=["广告组 ID"],
)

assert (
    "event",
    "adinfo",
    "$.adsetId",
    "adinfo.adsetId",
    "广告组 ID",
    "文本",
    "广告组标识说明",
) in json_rows

imported = next(item for item in parsed.editor.fields if item.field_name == "adinfo.adsetId")
assert imported.aliases == ["广告组 ID"]
assert imported.field_comment == "广告组标识说明"
```

增加一个空显示名断言，证明属性说明不会进入别名：

```python
assert field.aliases == []
assert field.field_comment == "来源字段 adinfo 中的 JSON 属性 adId"
```

- [ ] **Step 3: 运行测试并确认 RED**

Run:

```powershell
Set-Location backend
.\.venv\Scripts\python.exe -m pytest tests/test_tracking_excel.py -k "json_field_parsing" -q
```

Expected: FAIL；新版七列中的“字段显示名”没有进入 `aliases`，导出表头和行仍为六列。

- [ ] **Step 4: 实现七列 Excel 契约**

在 `backend/apps/system/crud/tracking_excel.py` 修改常量：

```python
JSON_FIELD_PARSING_COLUMNS = [
    "source_table",
    "source_field",
    "json_path",
    "field_name",
    "field_display_name",
    "field_type",
    "description",
]
JSON_FIELD_PARSING_HEADER_ALIASES = {
    "来源表": "source_table",
    "来源字段": "source_field",
    "json路径": "json_path",
    "生成字段名": "field_name",
    "字段显示名": "field_display_name",
    "类型": "field_type",
    "属性说明": "description",
}
JSON_FIELD_PARSING_EXPORT_COLUMN_LABELS = {
    "source_table": "来源表",
    "source_field": "来源字段",
    "json_path": "JSON路径",
    "field_name": "生成字段名",
    "field_display_name": "字段显示名",
    "field_type": "类型",
    "description": "属性说明",
}
```

`_field_item(...)` 已读取 `field_display_name` 并调用 `_aliases_from_row(...)`，不增加新的导入分支。

- [ ] **Step 5: 让独立 Sheet 的显示名成为权威值**

在 `_merge_json_sheet_field(...)` 的签名一致分支中补充：

```python
existing.aliases = list(field_item.aliases or [])
existing.field_comment = field_item.field_comment or existing.field_comment
existing.extra_properties = _merge_extra_properties(
    existing.extra_properties,
    field_item.extra_properties,
)
```

这一步只合并同一个 `table_name + field_name` 的一致 JSON 定义；来源字段、JSON 路径或类型冲突仍按现有逻辑失败。

- [ ] **Step 6: 导出主显示名**

在 `_json_field_parsing_rows(...)` 增加：

```python
{
    "source_table": _text(field_item.table_name),
    "source_field": _text(field_item.source_field),
    "json_path": _normalize_json_path(field_item.json_path),
    "field_name": _text(field_item.field_name),
    "field_display_name": _first_alias(field_item),
    "field_type": _json_field_type_for_export(field_item),
    "description": _text(field_item.field_comment),
}
```

不从 `field_comment` 生成显示名。

- [ ] **Step 7: 补齐旧五列和六列兼容测试**

使用 `SOURCE_TABLE_JSON_FIELD_PARSING_HEADERS` 构造旧六列工作簿，使用
`LEGACY_JSON_FIELD_PARSING_HEADERS` 构造旧五列工作簿。两种格式都断言：

```python
assert field.aliases == []
assert field.source_field == "userinfo"
assert field.json_path == "$.country"
```

- [ ] **Step 8: 更新用户文档**

在 `docs/generic_tracking_excel_template.md` 的 `JSON字段解析` 表格中，在“生成字段名”和“类型”之间加入：

```markdown
| 字段显示名 | 否 | 面向业务用户的主显示名称；为空时数据字典显示完整字段名，图表字段选择器显示 JSON 叶子属性名 |
```

同时把“新版六列”表述更新为“新版七列”，并明确旧五列、六列继续兼容。

- [ ] **Step 9: 运行 Task 1 测试并确认 GREEN**

Run:

```powershell
Set-Location backend
.\.venv\Scripts\python.exe -m pytest tests/test_tracking_excel.py -k "json_field_parsing or template_exports_json_dictionary_fields" -q
```

Expected: PASS；无 warning/error。

- [ ] **Step 10: 提交 Task 1**

```powershell
git add backend/apps/system/crud/tracking_excel.py backend/tests/test_tracking_excel.py docs/generic_tracking_excel_template.md
git commit -m "功能：保留 JSON 子字段显示名"
```

---

### Task 2: 后端区分 JSON 字段名称与说明

**Files:**
- Modify: `backend/tests/test_datasource_field_list_items.py`
- Modify: `backend/apps/datasource/api/datasource.py:481-494,630-704`

**Interfaces:**
- Consumes: `TenantTrackingFieldModel.aliases`、`field_comment`、`_field_list_item_from_core(...)`、`_field_list_item_from_tracking(...)`。
- Produces: `_tracking_display_name(row, *, allow_comment_fallback: bool = True) -> str | None`；JSON 派生字段传 `False`，物理字段保持默认 `True`。

- [ ] **Step 1: 写 JSON 无别名时不返回说明的失败测试**

在 `backend/tests/test_datasource_field_list_items.py` 导入 `SimpleNamespace` 和 `_field_list_item_from_tracking`：

```python
from types import SimpleNamespace

from apps.datasource.api.datasource import (
    _field_list_item_from_tracking,
    _tracking_display_name,
)
```

增加测试数据助手：

```python
def _tracking_json_field(*, aliases: list[str] | None = None):
    return SimpleNamespace(
        field_name="adinfo.adId",
        aliases=aliases or [],
        field_comment="来源字段 adinfo 中的 JSON 属性 adId",
        field_role="json_path_dimension",
        semantic_type="text",
        source_field="adinfo",
        json_path="$.adId",
        expression=None,
        category=None,
        value_mappings=None,
        example_values=None,
    )
```

增加行为测试：

```python
def test_tracking_json_field_does_not_use_comment_as_display_name() -> None:
    item = _field_list_item_from_tracking(
        _tracking_json_field(),
        datasource=SimpleNamespace(type="mysql", type_name="MySQL"),
        table=SimpleNamespace(table_name="event", ds_id=6, id=10),
        field_index=1,
    )

    assert item.display_name is None
    assert item.field_name == "adinfo.adId"
    assert item.custom_comment == "来源字段 adinfo 中的 JSON 属性 adId"


def test_tracking_json_field_prefers_explicit_alias() -> None:
    item = _field_list_item_from_tracking(
        _tracking_json_field(aliases=["广告 ID"]),
        datasource=SimpleNamespace(type="mysql", type_name="MySQL"),
        table=SimpleNamespace(table_name="event", ds_id=6, id=10),
        field_index=1,
    )

    assert item.display_name == "广告 ID"
```

增加物理字段兼容断言：

```python
def test_tracking_display_name_keeps_physical_comment_fallback() -> None:
    row = SimpleNamespace(aliases=[], field_comment="业务日期（分区字段），按天统计")
    assert _tracking_display_name(row) == "业务日期（分区字段）"
```

- [ ] **Step 2: 运行测试并确认 RED**

Run:

```powershell
Set-Location backend
.\.venv\Scripts\python.exe -m pytest tests/test_datasource_field_list_items.py -q
```

Expected: FAIL；JSON 派生字段当前把属性说明第一句返回为 `display_name`。

- [ ] **Step 3: 为显示名称助手增加显式回退开关**

修改 `backend/apps/datasource/api/datasource.py`：

```python
def _tracking_display_name(
    row: TenantTrackingFieldModel | None,
    *,
    allow_comment_fallback: bool = True,
) -> str | None:
    if row is None:
        return None
    for item in _tracking_json_list(row.aliases):
        text = str(item or "").strip()
        if text:
            return text
    if not allow_comment_fallback:
        return None
    comment = (row.field_comment or "").strip()
    if not comment:
        return None
    return re.split(r"[；;。，,\n]", comment, maxsplit=1)[0].strip() or None
```

物理字段调用保持：

```python
display_name = _tracking_display_name(tracking)
```

JSON 派生字段改为：

```python
display_name=_tracking_display_name(row, allow_comment_fallback=False),
```

- [ ] **Step 4: 运行 Task 2 测试并确认 GREEN**

Run:

```powershell
Set-Location backend
.\.venv\Scripts\python.exe -m pytest tests/test_datasource_field_list_items.py -q
```

Expected: PASS；JSON 字段说明保留在 `custom_comment`，不再进入 `display_name`；物理字段回退不变。

- [ ] **Step 5: 提交 Task 2**

```powershell
git add backend/apps/datasource/api/datasource.py backend/tests/test_datasource_field_list_items.py
git commit -m "修复：区分 JSON 字段名称与说明"
```

---

### Task 3: 图表字段选择器统一回退到 JSON 叶子名

**Files:**
- Modify: `frontend/src/views/dashboard/common/builderFieldPickerOptions.test.mjs`
- Modify: `frontend/src/views/dashboard/common/builderFieldPickerOptions.ts`
- Modify: `frontend/src/views/dashboard/common/BuilderFieldPicker.vue:4-45,230-238`

**Interfaces:**
- Consumes: `FieldOption` 的 `kind`、`displayName`、`label`、`field`、`sourceField`、`jsonPath`、`isJsonSubfield`。
- Produces: `fieldOptionDisplayName(option?: FieldOption, fallback?: string) -> string`，供已选值、下拉行、事件排序和悬停标题共同使用。

- [ ] **Step 1: 写字段名称纯函数的失败测试**

在 `builderFieldPickerOptions.test.mjs` 增加：

```javascript
assert.equal(
  options.fieldOptionDisplayName({
    label: 'adinfo.adId',
    value: 'event.adinfo.adId',
    table: 'event',
    field: 'adinfo.adId',
    displayName: '广告 ID',
    sourceField: 'adinfo',
    jsonPath: '$.adId',
    isJsonSubfield: true,
  }),
  '广告 ID',
  'JSON 子字段应优先显示显式业务名称'
)

assert.equal(
  options.fieldOptionDisplayName({
    label: 'adinfo.adId',
    value: 'event.adinfo.adId',
    table: 'event',
    field: 'adinfo.adId',
    sourceField: 'adinfo',
    jsonPath: '$.adId',
    isJsonSubfield: true,
  }),
  'adId',
  'JSON 子字段没有显示名时应显示叶子属性名'
)

assert.equal(
  options.fieldOptionDisplayName({
    label: '业务日期（分区字段）',
    value: 'event.dt',
    table: 'event',
    field: 'dt',
  }),
  '业务日期（分区字段）',
  '普通字段继续使用现有 label'
)
```

- [ ] **Step 2: 运行测试并确认 RED**

Run:

```powershell
Set-Location frontend
node src/views/dashboard/common/builderFieldPickerOptions.test.mjs
```

Expected: FAIL，提示 `fieldOptionDisplayName is not a function`。

- [ ] **Step 3: 实现可复用字段名称函数**

在 `builderFieldPickerOptions.ts` 增加：

```typescript
export function fieldOptionDisplayName(option?: FieldOption, fallback = '') {
  if (!option) {
    return fallback.split('.').pop() || ''
  }
  if (option.kind === 'tracking-event') {
    return option.displayName || option.label || option.eventName || option.field
  }
  if (
    isJsonSubfieldOption(option) &&
    option.sourceField &&
    option.field.startsWith(`${option.sourceField}.`)
  ) {
    const explicitLabel = option.label && option.label !== option.field ? option.label : ''
    return option.displayName || explicitLabel || option.field.slice(option.sourceField.length + 1)
  }
  return option.displayName || option.label || option.field
}
```

该函数只使用显式元数据判断 JSON 子字段，不通过业务字段名或表名猜测。

- [ ] **Step 4: 让组件所有名称位置使用同一函数**

修改 `BuilderFieldPicker.vue` 导入：

```typescript
import {
  fieldOptionDisplayName,
  isNumericFieldOption,
  isSelectableFieldOption,
  isTimeFieldOption,
} from './builderFieldPickerOptions'
```

把已选名称改为：

```typescript
const selectedLabel = computed(() =>
  fieldOptionDisplayName(selectedOption.value, props.modelValue)
)
```

删除组件内的 `displayFieldName(...)`，把事件排序、下拉主标题和悬停标题中的调用统一替换为 `fieldOptionDisplayName(...)`。

- [ ] **Step 5: 运行 Task 3 测试并确认 GREEN**

Run:

```powershell
Set-Location frontend
node src/views/dashboard/common/builderFieldPickerOptions.test.mjs
node src/views/dashboard/common/BuilderFieldPicker.style.test.mjs
```

Expected: 两个命令都退出码 0，无断言错误。

- [ ] **Step 6: 运行 TypeScript 和生产构建检查**

Run:

```powershell
Set-Location frontend
npm run build
```

Expected: `vue-tsc -b` 和 `vite build` 成功，无 TypeScript 错误。

- [ ] **Step 7: 提交 Task 3**

```powershell
git add frontend/src/views/dashboard/common/builderFieldPickerOptions.ts frontend/src/views/dashboard/common/builderFieldPickerOptions.test.mjs frontend/src/views/dashboard/common/BuilderFieldPicker.vue
git commit -m "修复：JSON 字段选择器回退属性名"
```

---

## Final Verification

- [ ] **Step 1: 运行后端聚焦回归测试**

```powershell
Set-Location backend
.\.venv\Scripts\python.exe -m pytest tests/test_tracking_excel.py tests/test_datasource_field_list_items.py -q
```

Expected: 全部 PASS，无失败和错误。

- [ ] **Step 2: 运行前端聚焦测试和构建**

```powershell
Set-Location frontend
node src/views/dashboard/common/builderFieldPickerOptions.test.mjs
node src/views/dashboard/common/BuilderFieldPicker.style.test.mjs
npm run build
```

Expected: 全部退出码 0。

- [ ] **Step 3: 检查工作簿往返结果**

使用 `tracking_config_excel(...)` 导出包含以下字段的测试配置：

```python
TenantTrackingFieldDTO(
    tenant_id=2001,
    table_name="event",
    field_name="adinfo.adId",
    field_comment="广告归因标识说明",
    semantic_type="text",
    source_field="adinfo",
    json_path="$.adId",
    aliases=["广告 ID"],
)
```

确认 `JSON字段解析` 行为：

```text
event | adinfo | $.adId | adinfo.adId | 广告 ID | 文本 | 广告归因标识说明
```

再次导入后确认 `aliases == ["广告 ID"]` 且 `field_comment == "广告归因标识说明"`。

- [ ] **Step 4: 检查两个页面的最终名称契约**

通过聚焦测试和当前代码确认：

```text
有显示名：数据字典 = 广告 ID；图表选择器 = 广告 ID
无显示名：数据字典 = adinfo.adId；图表选择器 = adId
说明文本：仅保留在 custom_comment/field_comment 和悬停说明中
```

- [ ] **Step 5: 检查未提交变更边界**

```powershell
git status --short
git diff --check
```

Expected: 只包含本计划源代码、测试和文档改动；不得包含用户现有的
`docs/superpowers/specs/2026-07-14-xiuxian-object-parameter-expansion-design.md` 或
`docs/xiuxian/tracking_dictionary_template_xiuxian_supplemented.xlsx`。
