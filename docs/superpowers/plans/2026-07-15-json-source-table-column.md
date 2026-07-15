# JSON 字段来源表列实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为 `JSON字段解析` Sheet 增加可见的第一列“来源表”，让 event/user 中同名 JSON 来源字段可以按各自结构无损导入、导出并参与 SQL 生成，同时兼容旧五列工作簿。

**Architecture:** 在现有专用 Sheet 解析链路中扩展列契约和来源表解析函数：显式来源表严格按物理 schema 校验，空值继续走默认事件表优先兼容逻辑。导出器不再按来源字段跨表合并，而是按 `table_name + source_field + json_path + field_name` 稳定输出六列；数据库模型、SQL 方言编译器和前端上传入口保持不变。

**Tech Stack:** Python 3.11、Pydantic DTO、openpyxl、pytest

## Global Constraints

- `来源表`必须是 `JSON字段解析` Sheet 的可见第一列，不设置 hidden 属性。
- 显式来源表必须存在于 `physical_schema`，并且确实包含该行的`来源字段`。
- 旧五列工作簿或空`来源表`继续按默认事件表优先规则解析。
- event/user 同名来源字段按表分别保存和导出，不跨表去重。
- 不修改数据库模型、数据库迁移、SQL 方言编译器、前端上传入口。
- 不为修仙项目硬编码表名、字段名或业务口径。

---

### Task 1: 显式来源表导入与旧五列兼容

**Files:**
- Modify: `backend/apps/system/crud/tracking_excel.py:128`
- Modify: `backend/apps/system/crud/tracking_excel.py:1535`
- Modify: `backend/apps/system/crud/tracking_excel.py:1613`
- Test: `backend/tests/test_tracking_excel.py:93`
- Test: `backend/tests/test_tracking_excel.py:116`

**Interfaces:**
- Consumes: `_read_sheet_rows(...)` 通过 `JSON_FIELD_PARSING_HEADER_ALIASES` 生成的行字典，以及 `physical_schema: dict[str, PhysicalTableInfo]`。
- Produces: `_resolve_json_field_table(source_field, *, explicit_table, imported, existing, physical_schema, row_number) -> str`，返回严格校验后的字段归属表。

- [ ] **Step 1: 将测试工作簿助手扩展为同时生成新版六列与旧版五列**

```python
JSON_FIELD_PARSING_HEADERS = [
    "来源表",
    "来源字段",
    "JSON路径",
    "生成字段名",
    "类型",
    "属性说明",
]
LEGACY_JSON_FIELD_PARSING_HEADERS = JSON_FIELD_PARSING_HEADERS[1:]


def _json_overview_workbook(
    rows: list[list[object]],
    *,
    headers: list[str] = JSON_FIELD_PARSING_HEADERS,
) -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "JSON字段解析"
    sheet.append(headers)
    for row in rows:
        sheet.append(row)
    output = BytesIO()
    workbook.save(output)
    return output.getvalue()
```

- [ ] **Step 2: 写入显式 event/user 分表、非法来源表和旧五列兼容的失败测试**

```python
def test_json_field_parsing_sheet_honors_explicit_source_table() -> None:
    parsed = parse_tracking_excel(
        _json_overview_workbook([
            ["event", "userinfo", "$.country", "userinfo.country", "文本", "事件国家"],
            ["user", "userinfo", "$.country_code", "userinfo.country_code", "文本", "注册国家码"],
        ]),
        TenantTrackingConfigDTO(tenant_id=2001, enabled=True, default_event_table="event"),
        physical_schema=_json_overview_physical_schema(),
        datasource_type="mysql",
    )

    fields = {(item.table_name, item.field_name): item for item in parsed.editor.fields}
    assert fields[("event", "userinfo.country")].json_path == "$.country"
    assert fields[("user", "userinfo.country_code")].json_path == "$.country_code"


@pytest.mark.parametrize(
    ("table_name", "source_field", "message"),
    [
        ("missing", "userinfo", r"第 2 行.*来源表 missing.*不存在"),
        ("user", "event_only", r"第 2 行.*来源表 user.*不包含来源字段 event_only"),
    ],
)
def test_json_field_parsing_sheet_rejects_invalid_explicit_source_table(
    table_name: str,
    source_field: str,
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        parse_tracking_excel(
            _json_overview_workbook([
                [table_name, source_field, "$.country", f"{source_field}.country", "文本", "国家"],
            ]),
            TenantTrackingConfigDTO(tenant_id=2001, enabled=True, default_event_table="event"),
            physical_schema=_json_overview_physical_schema(),
            datasource_type="mysql",
        )


def test_json_field_parsing_sheet_legacy_five_columns_still_prefers_event() -> None:
    parsed = parse_tracking_excel(
        _json_overview_workbook(
            [["userinfo", "$.country", "userinfo.country", "文本", "国家"]],
            headers=LEGACY_JSON_FIELD_PARSING_HEADERS,
        ),
        TenantTrackingConfigDTO(tenant_id=2001, enabled=True, default_event_table="event"),
        physical_schema=_json_overview_physical_schema(),
        datasource_type="mysql",
    )

    field = next(item for item in parsed.editor.fields if item.field_name == "userinfo.country")
    assert field.table_name == "event"
```

- [ ] **Step 3: 运行新增导入测试并确认失败原因来自缺少来源表支持**

Run: `D:\AIWork3\chat-bi\backend\.venv\Scripts\python.exe -m pytest tests/test_tracking_excel.py -k "explicit_source_table or legacy_five_columns" -q`

Expected: 新六列测试失败，错误表现为表头/数据错位或未按显式 `user` 表归属；旧五列兼容测试仍通过。

- [ ] **Step 4: 扩展列映射和来源表解析器**

```python
JSON_FIELD_PARSING_COLUMNS = [
    "source_table",
    "source_field",
    "json_path",
    "field_name",
    "field_type",
    "description",
]
JSON_FIELD_PARSING_HEADER_ALIASES = {
    "来源表": "source_table",
    "来源字段": "source_field",
    "json路径": "json_path",
    "生成字段名": "field_name",
    "类型": "field_type",
    "属性说明": "description",
}


def _resolve_json_field_table(
    source_field: str,
    *,
    explicit_table: str,
    imported: TenantTrackingConfigEditor,
    existing: TenantTrackingConfigDTO,
    physical_schema: dict[str, PhysicalTableInfo],
    row_number: int,
) -> str:
    if explicit_table:
        if explicit_table not in physical_schema:
            raise ValueError(
                f"{JSON_FIELD_PARSING_SHEET} sheet 第 {row_number} 行："
                f"来源表 {explicit_table} 不存在于当前物理 schema。"
            )
        table_fields = {
            item.field_name for item in physical_schema[explicit_table].fields
        }
        if source_field not in table_fields:
            raise ValueError(
                f"{JSON_FIELD_PARSING_SHEET} sheet 第 {row_number} 行："
                f"来源表 {explicit_table} 不包含来源字段 {source_field}。"
            )
        return explicit_table

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
```

在 `_parse_json_field_parsing_sheet(...)` 中读取并传入显式来源表：

```python
explicit_table = _text(row.get("source_table"))
table_name = _resolve_json_field_table(
    source_field,
    explicit_table=explicit_table,
    imported=editor,
    existing=existing,
    physical_schema=physical_schema,
    row_number=row_number,
)
```

- [ ] **Step 5: 运行导入相关测试并确认通过**

Run: `D:\AIWork3\chat-bi\backend\.venv\Scripts\python.exe -m pytest tests/test_tracking_excel.py -k "json_field_parsing_sheet" -q`

Expected: 所有 `json_field_parsing_sheet` 测试通过。

- [ ] **Step 6: 提交导入实现**

```powershell
git add backend/apps/system/crud/tracking_excel.py backend/tests/test_tracking_excel.py
git commit -m "功能：支持 JSON 字段显式来源表导入"
```

### Task 2: 六列可见导出与分表往返

**Files:**
- Modify: `backend/apps/system/crud/tracking_excel.py:154`
- Modify: `backend/apps/system/crud/tracking_excel.py:2666`
- Modify: `backend/apps/system/crud/tracking_excel.py:2685`
- Test: `backend/tests/test_tracking_excel.py:1433`
- Test: `backend/tests/test_tracking_excel.py:1497`
- Test: `backend/tests/test_tracking_excel.py:1558`
- Modify: `docs/generic_tracking_excel_template.md:67`

**Interfaces:**
- Consumes: `config.fields` 中具有 `table_name/source_field/json_path/semantic_type` 的 JSON 字典字段。
- Produces: `_json_field_parsing_rows(config, *, event_table) -> list[dict[str, Any]]` 的六列行字典；保留 `event_table` 形参以避免扩大调用改动，但排序不再依赖 event 优先去重。

- [ ] **Step 1: 将导出断言更新为六列并写入跨表不同结构往返失败测试**

```python
def test_json_field_parsing_export_keeps_cross_table_source_definitions() -> None:
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

    output = tracking_config_excel(config, physical_schema=schema).getvalue()
    assert _headers(output, "JSON字段解析") == JSON_FIELD_PARSING_HEADERS
    assert _sheet_rows(output, "JSON字段解析") == [
        ("event", "payload", "$.event_key", "payload.event_key", "文本", None),
        ("user", "payload", "$.user_key", "payload.user_key", "文本", None),
    ]

    workbook = load_workbook(BytesIO(output))
    assert workbook["JSON字段解析"].column_dimensions["A"].hidden is not True

    parsed = parse_tracking_excel(
        output,
        TenantTrackingConfigDTO(tenant_id=2001, enabled=True, default_event_table="event"),
        physical_schema=schema,
        datasource_type="mysql",
    )
    imported = {(item.table_name, item.field_name) for item in parsed.editor.fields}
    assert ("event", "payload.event_key") in imported
    assert ("user", "payload.user_key") in imported
```

同时把已有空值类型期望更新为：

```python
assert _sheet_rows(output, "JSON字段解析") == [
    ("event", "allianceinfo", "$.power", "allianceinfo.power", "空值", None),
]
```

- [ ] **Step 2: 运行导出测试并确认旧冲突错误与五列表头导致失败**

Run: `D:\AIWork3\chat-bi\backend\.venv\Scripts\python.exe -m pytest tests/test_tracking_excel.py -k "json_field_parsing_export or template_exports_json" -q`

Expected: 跨表测试在 `_json_field_parsing_rows(...)` 的冲突异常处失败，表头仍缺少`来源表`。

- [ ] **Step 3: 将导出列改为六列并按表稳定输出所有 JSON 字段**

```python
JSON_FIELD_PARSING_EXPORT_COLUMN_LABELS = {
    "source_table": "来源表",
    "source_field": "来源字段",
    "json_path": "JSON路径",
    "field_name": "生成字段名",
    "field_type": "类型",
    "description": "属性说明",
}


def _json_field_parsing_rows(
    config: TenantTrackingConfigDTO,
    *,
    event_table: str,
) -> list[dict[str, Any]]:
    del event_table
    rows = [
        {
            "source_table": _text(field_item.table_name),
            "source_field": _text(field_item.source_field),
            "json_path": _normalize_json_path(field_item.json_path),
            "field_name": _text(field_item.field_name),
            "field_type": _json_field_type_for_export(field_item),
            "description": _text(field_item.field_comment),
        }
        for field_item in config.fields or []
        if _is_json_dictionary_field(field_item)
    ]
    return sorted(
        rows,
        key=lambda row: (
            _text(row["source_table"]),
            _text(row["source_field"]),
            _text(row["json_path"]),
            _text(row["field_name"]),
        ),
    )
```

删除仅服务于旧跨表冲突判断的 `_json_field_export_signature(...)`。不要设置 `JSON字段解析` Sheet 的 A 列隐藏属性。

- [ ] **Step 4: 运行全部 tracking Excel 测试并确认通过**

Run: `D:\AIWork3\chat-bi\backend\.venv\Scripts\python.exe -m pytest tests/test_tracking_excel.py -q`

Expected: 该文件全部测试通过；基线数量不少于 42 项。

- [ ] **Step 5: 更新维护文档的六列契约与兼容规则**

将 `docs/generic_tracking_excel_template.md` 的 `JSON字段解析` 表格和导入映射改为：

```markdown
| 来源表 | 否 | JSON 来源字段所在物理表；显式填写时必须存在且包含来源字段 |
| 来源字段 | 是 | 承载 JSON 文本的物理字段，例如 `userinfo`、`payload` |
| JSON路径 | 是 | 规范 JSON 路径，例如 `$._appVersion`、`$.items[0].sku` |
| 生成字段名 | 是 | 可查询字段名，必须与来源字段和路径一致，例如 `userinfo._appVersion` |
| 类型 | 是 | 文本、数值、布尔、时间、数组、对象或空值 |
| 属性说明 | 否 | 字段业务说明，进入字段注释和语义上下文 |
```

明确说明显式来源表优先且严格校验；旧五列或空来源表使用默认事件表优先；导出首列可见，event/user 同名来源字段逐表输出。

- [ ] **Step 6: 运行联合回归和真实修仙工作簿往返验证**

Run: `D:\AIWork3\chat-bi\backend\.venv\Scripts\python.exe -m pytest tests/test_tracking_excel.py tests/test_tracking_config_api.py tests/test_tracking_config_service.py -q`

Expected: 联合回归全部通过，基线数量不少于 69 项。

Run: 使用现有测试辅助脚本或一次性只读校验代码导入 `docs/xiuxian/tracking_dictionary_template_xiuxian_supplemented.xlsx`，再导出并重新导入；检查有效 JSON 字段数保持 160，`power/abtest` 两条空路径仍告警跳过，导出首列为`来源表`且 A 列未隐藏。

Expected: 两次导入均得到 160 条有效 JSON 字段，跨表字段的 `table_name` 保持不变，导出工作簿可以被 openpyxl 正常重新打开。

- [ ] **Step 7: 提交导出、文档和回归测试**

```powershell
git add backend/apps/system/crud/tracking_excel.py backend/tests/test_tracking_excel.py docs/generic_tracking_excel_template.md
git commit -m "功能：按来源表导出 JSON 字段解析"
```

