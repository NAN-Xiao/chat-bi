# JSON 字段解析 Sheet 导入导出闭环 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让平台直接导入和导出独立的 `JSON字段解析` Sheet，并使其中的有效字段进入现有 JSON SQL 生成链路。

**Architecture:** 在 `tracking_excel.py` 内增加固定 Sheet 契约和专用解析器，复用现有 `_field_item(...)`、字段配置模型与运行时 JSON 表达式编译器。导入时先解析物理表，再解析独立 Sheet；导出时把带 `source_field/json_path` 的普通字段集中写入独立 Sheet，并从 `event/user` 属性 Sheet 排除。通用表保留枚举兼容行，但独立 Sheet 的字段集合保持权威。

**Tech Stack:** Python 3.11、pandas、openpyxl、xlsxwriter、Pydantic、pytest。

## Global Constraints

- `JSON字段解析` 固定列为：`来源字段`、`JSON路径`、`生成字段名`、`类型`、`属性说明`。
- 工作簿不增加“来源表”列；同名来源字段优先归属默认事件表。
- 空 JSON 路径或空生成字段名行必须警告并跳过，不生成 SQL 字段。
- 不修改数据库模型、迁移、前端上传入口和 `compile_tracking_json_expression(...)`。
- 不硬编码 `event`、`user`、修仙字段名或客户业务口径；使用默认事件表和物理 schema 消歧。
- 独立 Sheet 存在时，其 JSON 字段定义与物理表 Sheet 的同名定义必须一致，否则明确失败。
- 没有独立 Sheet 的现有工作簿继续按原规则导入。
- 所有生产代码必须先有按预期失败的回归测试。

---

## File Structure

- `backend/apps/system/crud/tracking_excel.py`：定义独立 Sheet 契约、导入解析、来源表消歧、冲突校验和导出行构造。
- `backend/tests/test_tracking_excel.py`：覆盖导入、校验、导出、往返和 SQL 表达式集成。
- `docs/generic_tracking_excel_template.md`：记录新的固定 Sheet、字段规则、错误行为和导入导出职责。

### Task 1: 识别并导入独立 JSON 字段 Sheet

**Files:**
- Modify: `backend/tests/test_tracking_excel.py`
- Modify: `backend/apps/system/crud/tracking_excel.py:29-60`
- Modify: `backend/apps/system/crud/tracking_excel.py:485-555`
- Modify: `backend/apps/system/crud/tracking_excel.py:1649-1755`

**Interfaces:**
- Consumes: `parse_tracking_excel(content, existing, physical_schema=..., datasource_type=...)`、`_field_item(...)`、`_normalize_json_path(...)`。
- Produces: `JSON_FIELD_PARSING_SHEET`、`JSON_FIELD_PARSING_COLUMNS`、`_parse_json_field_parsing_sheet(...) -> int`。

- [ ] **Step 1: 写入导入失败测试和测试 schema**

在 `backend/tests/test_tracking_excel.py` 增加导入和 SQL 集成测试：

```python
from apps.system.crud.tracking_expression import compile_tracking_json_expression


JSON_FIELD_PARSING_HEADERS = ["来源字段", "JSON路径", "生成字段名", "类型", "属性说明"]


def _json_overview_physical_schema() -> dict[str, PhysicalTableInfo]:
    return {
        "event": PhysicalTableInfo(
            table_name="event",
            fields=[
                PhysicalFieldInfo("uid", "varchar", "用户ID"),
                PhysicalFieldInfo("event", "varchar", "事件名"),
                PhysicalFieldInfo("userinfo", "text", "用户信息 JSON"),
                PhysicalFieldInfo("event_only", "text", "事件独有 JSON"),
            ],
        ),
        "user": PhysicalTableInfo(
            table_name="user",
            fields=[
                PhysicalFieldInfo("uid", "varchar", "用户ID"),
                PhysicalFieldInfo("userinfo", "text", "用户信息 JSON"),
                PhysicalFieldInfo("profile_json", "text", "用户独有 JSON"),
            ],
        ),
    }


def _json_overview_workbook(rows: list[list[object]]) -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "JSON字段解析"
    sheet.append(JSON_FIELD_PARSING_HEADERS)
    for row in rows:
        sheet.append(row)
    output = BytesIO()
    workbook.save(output)
    return output.getvalue()


def test_json_field_parsing_sheet_imports_fields_and_prefers_event_table() -> None:
    parsed = parse_tracking_excel(
        _json_overview_workbook([
            ["userinfo", "$._appVersion", "userinfo._appVersion", "文本", "应用版本"],
            ["profile_json", "$.country", "profile_json.country", "文本", "注册国家"],
        ]),
        TenantTrackingConfigDTO(
            tenant_id=2001,
            enabled=True,
            default_event_table="event",
        ),
        physical_schema=_json_overview_physical_schema(),
        datasource_type="mysql",
    )

    fields = {(item.table_name, item.field_name): item for item in parsed.editor.fields}
    app_version = fields[("event", "userinfo._appVersion")]
    assert app_version.source_field == "userinfo"
    assert app_version.json_path == "$._appVersion"
    assert app_version.semantic_type == "text"
    assert app_version.field_comment == "应用版本"
    assert ("user", "profile_json.country") in fields
    assert not any(item.table_name == "JSON字段解析" for item in parsed.editor.tables)

    expression = compile_tracking_json_expression(
        app_version.table_name,
        app_version.source_field,
        app_version.json_path,
        app_version.semantic_type,
        "mysql",
    )
    assert expression == "JSON_UNQUOTE(JSON_EXTRACT(`event`.`userinfo`, '$._appVersion'))"
```

- [ ] **Step 2: 运行测试并确认按预期失败**

Run:

```powershell
backend\.venv\Scripts\python.exe -m pytest backend/tests/test_tracking_excel.py::test_json_field_parsing_sheet_imports_fields_and_prefers_event_table -q
```

Expected: FAIL，因为当前解析器把 `JSON字段解析` 当作普通业务表，结果中不存在 `("event", "userinfo._appVersion")`。

- [ ] **Step 3: 增加固定 Sheet 契约和上下文表头解析**

在 `tracking_excel.py` 增加：

```python
JSON_FIELD_PARSING_SHEET = "JSON字段解析"
JSON_FIELD_PARSING_COLUMNS = [
    "source_field",
    "json_path",
    "field_name",
    "field_type",
    "description",
]
JSON_FIELD_PARSING_HEADER_ALIASES = {
    "来源字段": "source_field",
    "json路径": "json_path",
    "生成字段名": "field_name",
    "类型": "field_type",
    "属性说明": "description",
}
JSON_OBSERVED_TYPE_KEY = "json_observed_type"
```

把 `JSON_FIELD_PARSING_SHEET` 加入 `SYSTEM_SHEETS`。给 `_canonical_header(...)` 和
`_read_sheet_rows(...)` 增加可选参数：

```python
def _canonical_header(
    value: Any,
    header_aliases: dict[str, str] | None = None,
) -> str:
    key = _header_key(value)
    if not key:
        return ""
    if header_aliases and key in header_aliases:
        return header_aliases[key]
    return HEADER_ALIASES.get(key, _text(value))


def _read_sheet_rows(
    excel: pd.ExcelFile,
    sheet_name: str,
    *,
    require_recognized_header: bool = False,
    include_row_number: bool = False,
    header_aliases: dict[str, str] | None = None,
) -> tuple[list[dict[str, Any]], int]:
    raw = pd.read_excel(excel, sheet_name=sheet_name, header=None, dtype=object).fillna("")
    if raw.empty:
        return [], 0

    recognized_headers = (
        set(HEADER_ALIASES.values())
        | set((header_aliases or {}).values())
        | set(BUSINESS_COLUMNS)
    )
    header_index = None
    for index, row in raw.iterrows():
        headers = [
            _canonical_header(value, header_aliases)
            for value in row.tolist()
        ]
        known_count = sum(1 for value in headers if value in recognized_headers)
        if known_count >= 2:
            header_index = int(index)
            break

    if header_index is None:
        nonempty_row_count = sum(
            1
            for _, row in raw.iterrows()
            if any(_text(value) for value in row.tolist())
        )
        if require_recognized_header and nonempty_row_count > 1:
            raise ValueError(f"{sheet_name} sheet 表头无法识别，请使用平台导出的固定表头。")
        return [], len(raw.index)

    canonical_headers: list[str] = []
    used: dict[str, int] = {}
    for value in raw.iloc[header_index].tolist():
        header = _canonical_header(value, header_aliases)
        if not header:
            canonical_headers.append("")
            continue
        count = used.get(header, 0) + 1
        used[header] = count
        canonical_headers.append(header if count == 1 else f"{header}_{count}")

    rows: list[dict[str, Any]] = []
    skipped = 0
    for raw_index, raw_row in raw.iloc[header_index + 1 :].iterrows():
        row: dict[str, Any] = {}
        has_value = False
        for col_index, header in enumerate(canonical_headers):
            if not header:
                continue
            value = raw_row.iloc[col_index]
            row[header] = value
            if _text(value):
                has_value = True
        if has_value:
            if include_row_number:
                row[EXCEL_ROW_NUMBER_KEY] = int(raw_index) + 1
            rows.append(row)
        else:
            skipped += 1
    return rows, skipped
```

表头识别的 `known_count` 同时包含 `HEADER_ALIASES.values()` 和
`header_aliases.values()`，保证五列表头可以被可靠识别。

- [ ] **Step 4: 实现来源表解析和最小导入逻辑**

增加：

```python
def _resolve_json_field_table(
    source_field: str,
    *,
    imported: TenantTrackingConfigEditor,
    existing: TenantTrackingConfigDTO,
    physical_schema: dict[str, PhysicalTableInfo],
    row_number: int,
) -> str:
    candidates = [
        table_name
        for table_name, table_info in physical_schema.items()
        if source_field in {item.field_name for item in table_info.fields}
    ]
    event_table = _text(imported.default_event_table) or _text(existing.default_event_table)
    if event_table in candidates:
        return event_table
    if len(candidates) == 1:
        return candidates[0]
    if not candidates:
        raise ValueError(
            f"{JSON_FIELD_PARSING_SHEET} sheet 第 {row_number} 行："
            f"来源字段 {source_field} 不存在于当前物理 schema。"
        )
    raise ValueError(
        f"{JSON_FIELD_PARSING_SHEET} sheet 第 {row_number} 行："
        f"来源字段 {source_field} 同时存在于 {', '.join(candidates)}，"
        "且无法按默认事件表消歧。"
    )


def _parse_json_field_parsing_sheet(
    rows: list[dict[str, Any]],
    editor: TenantTrackingConfigEditor,
    existing: TenantTrackingConfigDTO,
    *,
    datasource_type: str | None,
    warnings: list[str],
    physical_schema: dict[str, PhysicalTableInfo],
) -> int:
    skipped = 0
    for row in rows:
        row_number = int(row.get(EXCEL_ROW_NUMBER_KEY) or 0)
        source_field = _text(row.get("source_field"))
        json_path = _normalize_json_path(_text(row.get("json_path")))
        field_name = _text(row.get("field_name"))
        if not json_path or not field_name:
            _add_warning(
                warnings,
                f"{JSON_FIELD_PARSING_SHEET} sheet 第 {row_number} 行："
                f"来源字段 {source_field or '（空）'} 缺少 JSON路径或生成字段名，已跳过。",
            )
            skipped += 1
            continue
        table_name = _resolve_json_field_table(
            source_field,
            imported=editor,
            existing=existing,
            physical_schema=physical_schema,
            row_number=row_number,
        )
        observed_type = _text(row.get("field_type"))
        normalized = dict(row)
        normalized["row_type"] = "dictionary_field"
        normalized["semantic_type"] = (
            "text" if observed_type == "空值" else _semantic_type(observed_type)
        )
        if observed_type == "空值":
            normalized[JSON_OBSERVED_TYPE_KEY] = observed_type
        field_item = _field_item(
            normalized,
            table_name,
            row_type="dictionary_field",
            datasource_type=datasource_type,
            warnings=warnings,
            physical_schema=physical_schema,
        )
        if field_item:
            editor.fields.append(field_item)
    return skipped
```

在物理表 Sheet 循环结束后读取独立 Sheet，并把返回值累加到 `skipped_rows`：

```python
if JSON_FIELD_PARSING_SHEET in excel.sheet_names:
    rows, skipped = _read_sheet_rows(
        excel,
        JSON_FIELD_PARSING_SHEET,
        require_recognized_header=True,
        include_row_number=True,
        header_aliases=JSON_FIELD_PARSING_HEADER_ALIASES,
    )
    skipped_rows += skipped
    skipped_rows += _parse_json_field_parsing_sheet(
        rows,
        imported,
        existing,
        datasource_type=datasource_type,
        warnings=warnings,
        physical_schema=schema,
    )
```

- [ ] **Step 5: 运行导入测试并提交**

Run:

```powershell
backend\.venv\Scripts\python.exe -m pytest backend/tests/test_tracking_excel.py::test_json_field_parsing_sheet_imports_fields_and_prefers_event_table -q
```

Expected: `1 passed`。

Commit:

```powershell
git add backend/apps/system/crud/tracking_excel.py backend/tests/test_tracking_excel.py
git commit -m "功能：导入独立 JSON 字段解析表"
```

### Task 2: 严格校验空行、路径、类型和重复定义

**Files:**
- Modify: `backend/tests/test_tracking_excel.py`
- Modify: `backend/apps/system/crud/tracking_excel.py`

**Interfaces:**
- Consumes: Task 1 的 `_parse_json_field_parsing_sheet(...)` 和 `_resolve_json_field_table(...)`。
- Produces: `_expected_json_field_name(source_field: str, json_path: str) -> str`、`_merge_json_sheet_field(...) -> None`。

- [ ] **Step 1: 写入校验失败测试**

增加以下测试：

```python
def test_json_field_parsing_sheet_skips_incomplete_rows_and_preserves_null_type() -> None:
    parsed = parse_tracking_excel(
        _json_overview_workbook([
            ["userinfo", "$._appVersion", "userinfo._appVersion", "空值", "尚无非空样本"],
            ["userinfo", "", "", "文本", "空对象，暂不生成字段"],
        ]),
        TenantTrackingConfigDTO(tenant_id=2001, enabled=True, default_event_table="event"),
        physical_schema=_json_overview_physical_schema(),
        datasource_type="mysql",
    )
    field = next(item for item in parsed.editor.fields if item.field_name == "userinfo._appVersion")
    assert field.semantic_type == "text"
    assert field.extra_properties["json_observed_type"] == "空值"
    assert parsed.skipped_rows == 1
    assert any("第 3 行" in warning and "已跳过" in warning for warning in parsed.warnings)


def test_json_field_parsing_sheet_rejects_generated_name_mismatch() -> None:
    with pytest.raises(ValueError, match="第 2 行.*生成字段名.*userinfo\\.country"):
        parse_tracking_excel(
            _json_overview_workbook([
                ["userinfo", "$.country", "userinfo.wrong", "文本", "国家"],
            ]),
            TenantTrackingConfigDTO(tenant_id=2001, enabled=True, default_event_table="event"),
            physical_schema=_json_overview_physical_schema(),
            datasource_type="mysql",
        )


def test_json_field_parsing_sheet_rejects_ambiguous_source_without_event_candidate() -> None:
    schema = {
        "profile_a": PhysicalTableInfo("profile_a", fields=[PhysicalFieldInfo("payload", "text")]),
        "profile_b": PhysicalTableInfo("profile_b", fields=[PhysicalFieldInfo("payload", "text")]),
    }
    with pytest.raises(ValueError, match="第 2 行.*profile_a.*profile_b"):
        parse_tracking_excel(
            _json_overview_workbook([["payload", "$.country", "payload.country", "文本", "国家"]]),
            TenantTrackingConfigDTO(tenant_id=2001, enabled=True),
            physical_schema=schema,
            datasource_type="mysql",
        )
```

再增加一个工作簿同时含 `event` 属性 Sheet 和 `JSON字段解析` 的测试：

```python
def _json_overview_with_event_field(*, event_type: str, overview_type: str) -> bytes:
    workbook = Workbook()
    event_sheet = workbook.active
    event_sheet.title = "event"
    event_sheet.append([
        "属性名（必填）",
        "属性显示名",
        "属性类型（必填）",
        "更新方式",
        "属性说明",
        "属性标签",
    ])
    event_sheet.append(["userinfo.country", "国家", event_type, "", "国家", "用户"])
    overview = workbook.create_sheet("JSON字段解析")
    overview.append(JSON_FIELD_PARSING_HEADERS)
    overview.append(["userinfo", "$.country", "userinfo.country", overview_type, "注册国家"])
    output = BytesIO()
    workbook.save(output)
    return output.getvalue()


def test_json_field_parsing_sheet_deduplicates_matching_table_definition() -> None:
    parsed = parse_tracking_excel(
        _json_overview_with_event_field(event_type="文本", overview_type="文本"),
        TenantTrackingConfigDTO(tenant_id=2001, enabled=True, default_event_table="event"),
        physical_schema=_json_overview_physical_schema(),
        datasource_type="mysql",
    )
    matches = [item for item in parsed.editor.fields if item.field_name == "userinfo.country"]
    assert len(matches) == 1
    assert matches[0].field_comment == "注册国家"


def test_json_field_parsing_sheet_rejects_conflicting_table_definition() -> None:
    with pytest.raises(ValueError, match="定义冲突"):
        parse_tracking_excel(
            _json_overview_with_event_field(event_type="数值", overview_type="文本"),
            TenantTrackingConfigDTO(tenant_id=2001, enabled=True, default_event_table="event"),
            physical_schema=_json_overview_physical_schema(),
            datasource_type="mysql",
        )
```

- [ ] **Step 2: 运行新增测试并确认失败原因**

Run:

```powershell
backend\.venv\Scripts\python.exe -m pytest backend/tests/test_tracking_excel.py -k "json_field_parsing_sheet and (skips or rejects or duplicate)" -q
```

Expected: 字段名不一致和重复定义冲突测试 FAIL；不能因为测试构造或表头错误而 ERROR。

- [ ] **Step 3: 实现规范字段名和冲突校验**

增加：

```python
def _expected_json_field_name(source_field: str, json_path: str) -> str:
    path = _normalize_json_path(json_path)
    if not source_field or not path or path == "$":
        return ""
    return f"{source_field}{path[1:]}"


def _merge_json_sheet_field(
    editor: TenantTrackingConfigEditor,
    field_item: TenantTrackingFieldBase,
    *,
    row_number: int,
) -> None:
    existing = next(
        (
            item
            for item in editor.fields
            if item.table_name == field_item.table_name
            and item.field_name == field_item.field_name
        ),
        None,
    )
    if existing is None:
        editor.fields.append(field_item)
        return
    old_signature = (
        _text(existing.source_field),
        _normalize_json_path(existing.json_path),
        _text(existing.semantic_type),
    )
    new_signature = (
        _text(field_item.source_field),
        _normalize_json_path(field_item.json_path),
        _text(field_item.semantic_type),
    )
    if old_signature != new_signature:
        raise ValueError(
            f"{JSON_FIELD_PARSING_SHEET} sheet 第 {row_number} 行："
            f"{field_item.table_name}.{field_item.field_name} 与物理表 sheet 中的定义冲突。"
        )
    existing.field_comment = field_item.field_comment or existing.field_comment
    existing.extra_properties = _merge_extra_properties(
        existing.extra_properties,
        field_item.extra_properties,
    )
```

在构造字段前执行：

```python
raw_path = _text(row.get("json_path"))
json_path = _normalize_json_path(raw_path)
if raw_path and not json_path:
    raise ValueError(
        f"{JSON_FIELD_PARSING_SHEET} sheet 第 {row_number} 行：JSON路径 {raw_path} 无效。"
    )
expected_name = _expected_json_field_name(source_field, json_path)
if field_name != expected_name:
    raise ValueError(
        f"{JSON_FIELD_PARSING_SHEET} sheet 第 {row_number} 行："
        f"生成字段名应为 {expected_name}，实际为 {field_name}。"
    )
```

最后使用 `_merge_json_sheet_field(...)`，不再直接 `editor.fields.append(...)`。

- [ ] **Step 4: 运行 JSON Sheet 测试和完整 tracking Excel 测试**

Run:

```powershell
backend\.venv\Scripts\python.exe -m pytest backend/tests/test_tracking_excel.py -k "json_field_parsing_sheet" -q
backend\.venv\Scripts\python.exe -m pytest backend/tests/test_tracking_excel.py -q
```

Expected: 两条命令均全部通过。

- [ ] **Step 5: 提交严格校验改动**

```powershell
git add backend/apps/system/crud/tracking_excel.py backend/tests/test_tracking_excel.py
git commit -m "修复：严格校验 JSON 字段解析定义"
```

### Task 3: 独立导出、物理 Sheet 排除和往返验证

**Files:**
- Modify: `backend/tests/test_tracking_excel.py:1210-1310`
- Modify: `backend/apps/system/crud/tracking_excel.py:120-220`
- Modify: `backend/apps/system/crud/tracking_excel.py:2418-2495`
- Modify: `backend/apps/system/crud/tracking_excel.py:2534-2583`
- Modify: `backend/apps/system/crud/tracking_excel.py:2728-2785`
- Modify: `backend/apps/system/crud/tracking_excel.py:2786-2895`

**Interfaces:**
- Consumes: `tracking_config_excel(...)`、Task 1 的固定 Sheet 常量、Task 2 保存的 `json_observed_type`。
- Produces: `_json_field_parsing_rows(...) -> list[dict[str, Any]]`、`_is_json_dictionary_field(...) -> bool`。

- [ ] **Step 1: 把现有模板字段测试改成独立 Sheet 期望**

先在 `test_template_contains_datasource_aligned_examples` 增加空总览断言：

```python
assert _headers(workbook_bytes, "JSON字段解析") == JSON_FIELD_PARSING_HEADERS
assert _sheet_rows(workbook_bytes, "JSON字段解析") == []
```

将 `test_template_keeps_existing_event_dictionary_fields` 改为：

```python
def test_template_exports_json_dictionary_fields_only_in_json_overview() -> None:
    # 保留原测试中 physical_schema 和 config 的完整构造，只替换导出后的断言。
    workbook_bytes = tracking_config_excel(
        config,
        physical_schema=physical_schema,
        template_only=True,
    ).getvalue()

    assert _headers(workbook_bytes, "JSON字段解析") == JSON_FIELD_PARSING_HEADERS
    json_rows = _sheet_rows(workbook_bytes, "JSON字段解析")
    assert ("adinfo", "$.adsetId", "adinfo.adsetId", "文本", "广告组ID") in json_rows
    assert ("allianceinfo", "$.allianceid", "allianceinfo.allianceid", "文本", "联盟ID") in json_rows
    assert ("personal", "$.nickname", "personal.nickname", "文本", "昵称") in json_rows

    assert "adinfo.adsetId" not in {row[0] for row in _sheet_rows(workbook_bytes, "event")}
    assert "allianceinfo.allianceid" not in {row[0] for row in _sheet_rows(workbook_bytes, "event")}
    assert "personal.nickname" not in {row[0] for row in _sheet_rows(workbook_bytes, "user")}

    parsed = parse_tracking_excel(
        workbook_bytes,
        TenantTrackingConfigDTO(tenant_id=2001, enabled=True, default_event_table="event"),
        physical_schema=physical_schema,
        datasource_type="postgresql",
    )
    imported = {
        (item.table_name, item.field_name, item.source_field, item.json_path)
        for item in parsed.editor.fields
    }
    assert ("event", "adinfo.adsetId", "adinfo", "$.adsetId") in imported
    assert ("user", "personal.nickname", "personal", "$.nickname") in imported
```

增加 `类型=空值` 往返测试和多表歧义导出失败测试：

```python
def test_json_field_parsing_export_preserves_observed_null_type() -> None:
    field = TenantTrackingFieldDTO(
        tenant_id=2001,
        table_name="event",
        field_name="allianceinfo.power",
        semantic_type="text",
        source_field="allianceinfo",
        json_path="$.power",
        extra_properties={"json_observed_type": "空值"},
    )
    output = tracking_config_excel(
        TenantTrackingConfigDTO(tenant_id=2001, default_event_table="event", fields=[field]),
        physical_schema={
            "event": PhysicalTableInfo("event", fields=[PhysicalFieldInfo("allianceinfo", "text")]),
        },
    ).getvalue()
    assert _sheet_rows(output, "JSON字段解析") == [
        ("allianceinfo", "$.power", "allianceinfo.power", "空值", None),
    ]


def test_json_field_parsing_export_rejects_cross_table_source_conflict() -> None:
    config = TenantTrackingConfigDTO(
        tenant_id=2001,
        default_event_table="event",
        fields=[
            TenantTrackingFieldDTO(
                tenant_id=2001,
                table_name="event",
                field_name="payload.event_key",
                semantic_type="text",
                source_field="payload",
                json_path="$.event_key",
            ),
            TenantTrackingFieldDTO(
                tenant_id=2001,
                table_name="user",
                field_name="payload.user_key",
                semantic_type="text",
                source_field="payload",
                json_path="$.user_key",
            ),
        ],
    )
    schema = {
        "event": PhysicalTableInfo("event", fields=[PhysicalFieldInfo("payload", "text")]),
        "user": PhysicalTableInfo("user", fields=[PhysicalFieldInfo("payload", "text")]),
    }
    with pytest.raises(ValueError, match="JSON字段解析.*payload.*event.*user"):
        tracking_config_excel(config, physical_schema=schema)
```

- [ ] **Step 2: 运行导出测试并确认失败**

Run:

```powershell
backend\.venv\Scripts\python.exe -m pytest backend/tests/test_tracking_excel.py -k "json_overview or json_field_parsing_export" -q
```

Expected: FAIL，因为导出中尚无 `JSON字段解析`，JSON 子字段仍位于 `event/user`。

- [ ] **Step 3: 实现导出行和固定表头**

增加导出标签和类型转换：

```python
JSON_FIELD_PARSING_EXPORT_COLUMN_LABELS = {
    "source_field": "来源字段",
    "json_path": "JSON路径",
    "field_name": "生成字段名",
    "field_type": "类型",
    "description": "属性说明",
}


def _is_json_dictionary_field(field_item: Any) -> bool:
    return bool(
        _text(getattr(field_item, "source_field", None))
        and _normalize_json_path(getattr(field_item, "json_path", None))
    )


def _json_field_type_for_export(field_item: Any) -> str:
    observed = _text(_extra_properties(field_item).get(JSON_OBSERVED_TYPE_KEY))
    if observed:
        return observed
    return _attribute_type_label(getattr(field_item, "semantic_type", None))
```

实现 `_json_field_parsing_rows(config, event_table=...)`：

```python
def _json_field_export_signature(field_item: Any) -> tuple[str, str, str, str]:
    return (
        _text(getattr(field_item, "field_name", None)),
        _normalize_json_path(getattr(field_item, "json_path", None)),
        _text(getattr(field_item, "semantic_type", None)),
        _text(getattr(field_item, "field_comment", None)),
    )


def _json_field_parsing_rows(
    config: TenantTrackingConfigDTO,
    *,
    event_table: str,
) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, list[Any]]] = {}
    for field_item in config.fields or []:
        if not _is_json_dictionary_field(field_item):
            continue
        source_field = _text(field_item.source_field)
        grouped.setdefault(source_field, {}).setdefault(
            _text(field_item.table_name), []
        ).append(field_item)

    selected: list[Any] = []
    for source_field, by_table in grouped.items():
        if len(by_table) == 1:
            selected.extend(next(iter(by_table.values())))
            continue
        if event_table not in by_table:
            raise ValueError(
                f"{JSON_FIELD_PARSING_SHEET} 无法表达来源字段 {source_field} 的多表归属："
                f"{', '.join(sorted(by_table))}。"
            )
        event_signatures = {
            _json_field_export_signature(item)
            for item in by_table[event_table]
        }
        for table_name, fields in by_table.items():
            if table_name == event_table:
                continue
            signatures = {_json_field_export_signature(item) for item in fields}
            if signatures != event_signatures:
                raise ValueError(
                    f"{JSON_FIELD_PARSING_SHEET} 无法表达来源字段 {source_field} "
                    f"在 {event_table} 与 {table_name} 中的不同定义。"
                )
        selected.extend(by_table[event_table])

    rows = [
        {
            "source_field": _text(field_item.source_field),
            "json_path": _normalize_json_path(field_item.json_path),
            "field_name": _text(field_item.field_name),
            "field_type": _json_field_type_for_export(field_item),
            "description": _text(field_item.field_comment),
        }
        for field_item in selected
    ]
    return sorted(
        rows,
        key=lambda row: (
            _text(row["source_field"]),
            _text(row["json_path"]),
            _text(row["field_name"]),
        ),
    )
```

在 `_export_header_label(...)` 最前面增加：

```python
if columns == JSON_FIELD_PARSING_COLUMNS:
    return JSON_FIELD_PARSING_EXPORT_COLUMN_LABELS.get(column, column)
```

- [ ] **Step 4: 从 event/user 属性 Sheet 排除 JSON 字典字段并添加新 Sheet**

在 `_attribute_sheet_rows_for_table(...)` 的 `configured_fields` 列表中增加：

```python
and not _is_json_dictionary_field(configured)
```

`_generic_sheet_rows_for_table(...)` 继续保留 JSON `dictionary_field/field_value` 兼容行，
避免五列总览丢失字段枚举；导入时按独立 Sheet 的权威字段集合清除已从总览删除的
普通 JSON 字段，并保留 `事件参数对照` 引用的事件专属属性。

在 `tracking_config_excel(...)` 解析出 `event_table` 后生成：

```python
json_field_rows = _json_field_parsing_rows(config, event_table=event_table)
```

把下列 Sheet 放在 `事件分组` 后、物理表 Sheet 前：

```python
(
    JSON_FIELD_PARSING_SHEET,
    json_field_rows,
    JSON_FIELD_PARSING_COLUMNS,
),
```

无 JSON 字段时仍输出五列表头。保持事件参数属性只由 `_event_parameter_mapping_rows(...)`
导出。

- [ ] **Step 5: 运行往返、完整测试并提交**

Run:

```powershell
backend\.venv\Scripts\python.exe -m pytest backend/tests/test_tracking_excel.py -k "json_overview or json_field_parsing_export or template_keeps_existing" -q
backend\.venv\Scripts\python.exe -m pytest backend/tests/test_tracking_excel.py -q
```

Expected: 两条命令全部通过。

Commit:

```powershell
git add backend/apps/system/crud/tracking_excel.py backend/tests/test_tracking_excel.py
git commit -m "功能：独立导出 JSON 字段解析表"
```

### Task 4: 文档、真实工作簿验收和回归验证

**Files:**
- Modify: `docs/generic_tracking_excel_template.md`
- Verify: `D:/AIWork3/djinchao/chat-bi/docs/xiuxian/tracking_dictionary_template_xiuxian_supplemented.xlsx`

**Interfaces:**
- Consumes: Task 1-3 完成后的 `parse_tracking_excel(...)` 和 `tracking_config_excel(...)`。
- Produces: 用户可维护的正式 Sheet 文档和真实工作簿验收证据。

- [ ] **Step 1: 更新模板文档**

在 `docs/generic_tracking_excel_template.md` 增加固定 Sheet 章节，明确：

```markdown
### `JSON字段解析`

该 Sheet 维护跨事件共享的普通 JSON 字典字段，固定列为“来源字段、JSON路径、
生成字段名、类型、属性说明”。来源字段同时存在于多张表时优先默认事件表；无法
消歧时导入失败。JSON路径或生成字段名为空的确认行会告警并跳过。

带 source_field/json_path 的普通字段导出时只出现在该 Sheet，不再写入 event/user
属性 Sheet。事件专属属性仍在“事件参数对照”维护。
```

在文档“工作簿结构”中把 `JSON字段解析` 加入系统 Sheet 清单；在“导入映射”中增加
`JSON字段解析 -> tracking_config.fields`；把“JSON 子字段必须维护在对应物理表 Sheet”
替换为“普通 JSON 子字段必须维护在 JSON字段解析，事件专属属性维护在事件参数对照”。

- [ ] **Step 2: 运行真实修仙工作簿只读验收**

从仓库根目录运行以下一次性只读脚本，不保存或覆盖工作簿：

```powershell
@'
from pathlib import Path
from io import BytesIO
from openpyxl import load_workbook
from apps.system.crud.tracking_excel import (
    PhysicalFieldInfo,
    PhysicalTableInfo,
    parse_tracking_excel,
)
from apps.system.schemas.tenant_schema import TenantTrackingConfigDTO

path = Path(r"D:\AIWork3\djinchao\chat-bi\docs\xiuxian\tracking_dictionary_template_xiuxian_supplemented.xlsx")
content = path.read_bytes()
workbook = load_workbook(BytesIO(content), read_only=True, data_only=True)
schema = {}
for table_name in ("event", "user"):
    sheet = workbook[table_name]
    fields = [
        PhysicalFieldInfo(str(row[0]), str(row[2] or ""))
        for row in sheet.iter_rows(min_row=2, values_only=True)
        if row[0]
    ]
    schema[table_name] = PhysicalTableInfo(table_name=table_name, fields=fields)

parsed = parse_tracking_excel(
    content,
    TenantTrackingConfigDTO(tenant_id=0, enabled=True, default_event_table="event"),
    physical_schema=schema,
    datasource_type="mysql",
)
json_fields = [item for item in parsed.editor.fields if item.source_field and item.json_path]
assert len(json_fields) == 160, len(json_fields)
assert any(item.field_name == "userinfo._appVersion" for item in json_fields)
assert any(item.field_name == "allianceinfo.power" for item in json_fields)
assert sum("缺少 JSON路径或生成字段名" in item for item in parsed.warnings) == 2
print("xiuxian_workbook_validation=PASS json_fields=160 skipped_placeholders=2")
'@ | backend\.venv\Scripts\python.exe -
```

Expected:

```text
xiuxian_workbook_validation=PASS json_fields=160 skipped_placeholders=2
```

- [ ] **Step 3: 运行最终回归命令**

Run:

```powershell
backend\.venv\Scripts\python.exe -m pytest backend/tests/test_tracking_excel.py backend/tests/test_sql_engine_context.py backend/tests/test_sql_json_paths.py backend/tests/test_datasource_field_list_items.py -q
git diff --check
git status --short
```

Expected: pytest 全部通过，`git diff --check` 无输出；`git status --short` 只显示本任务文档修改或仓库原有的 `.superpowers/` 未跟踪目录。

- [ ] **Step 4: 提交文档并复核提交范围**

```powershell
git add docs/generic_tracking_excel_template.md
git commit -m "文档：说明 JSON 字段解析表维护规则"
git log -4 --oneline
git status --short
```

Expected: 最近四个提交依次覆盖导入、校验、导出和文档；没有提交 `.superpowers/` 或其他无关文件。
