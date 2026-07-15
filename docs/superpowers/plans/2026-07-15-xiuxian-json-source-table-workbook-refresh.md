# 修仙 JSON 来源表工作簿刷新实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 重新采样 `xtxdj.event/user` 的文本 JSON 字段，排除 `personal`，并把 `tracking_dictionary_template_xiuxian_supplemented.xlsx` 的 `JSON字段解析` 更新为包含可见“来源表”首列的六列结构。

**Architecture:** 复用已验证的只读采样器，但把来源列选择规则改为 event/user 分别保留，不再按同名字段 event 优先去重。使用用户已授权的 Python/openpyxl 兜底流程原子更新现有工作簿，只重写 `JSON字段解析` Sheet 的值和必要样式；采样摘要、原始样例和数据库凭据只存在 `.codex-runtime`，不提交。

**Tech Stack:** Python 3、PyMySQL、openpyxl、pytest、LibreOffice（可用时用于视觉渲染）

## Global Constraints

- 数据库只读采样，不执行写 SQL。
- 采样范围锚定最大业务日期的最近 28 天，每个来源字段最多读取 5000 个非空值。
- 只处理 `event`、`user` 的字符类型字段，明确排除 `personal`。
- event/user 同名来源字段分别采样并写入，使用“来源表”消歧。
- 输出列固定为：`来源表、来源字段、JSON路径、生成字段名、类型、属性说明`。
- 不写入样例值、路径形态、采样命中数和备注。
- 保留已有属性说明；新路径优先复用同叶子字段说明，否则生成简短属性说明。
- 目标工作簿固定为 `docs/xiuxian/tracking_dictionary_template_xiuxian_supplemented.xlsx`。
- 不修改其它 Sheet 的名称、顺序、值、合并区域和关键样式。
- 数据库凭据只通过进程环境变量传入，不写入文件或日志。

---

### Task 1: 分表采样规则与最新数据库摘要

**Files:**
- Create temporary: `.codex-runtime/xiuxian-json-source-refresh/refresh_workbook.py`
- Create temporary: `.codex-runtime/xiuxian-json-source-refresh/test_refresh_workbook.py`
- Create temporary: `.codex-runtime/xiuxian-json-source-refresh/sample-summary.json`
- Read: `D:/AIWork3/djinchao/chat-bi/docs/xiuxian/task-2-final-build_json_overview.py`

**Interfaces:**
- Produces: `resolve_source_columns(event_columns: list[str], user_columns: list[str]) -> list[tuple[str, str]]`
- Produces: `sample-summary.json`，包含 `anchor_dt/start_dt/selected_columns/rows`。

- [ ] **Step 1: 写入同名字段分表保留的失败测试**

```python
def test_resolve_source_columns_keeps_same_field_for_both_tables():
    assert resolve_source_columns(
        ["userinfo", "deviceinfo", "personal"],
        ["userinfo", "accountinfo", "personal"],
    ) == [
        ("event", "deviceinfo"),
        ("event", "userinfo"),
        ("user", "accountinfo"),
        ("user", "userinfo"),
    ]
```

- [ ] **Step 2: 运行测试确认旧 event 优先规则失败**

Run: `D:/AIWork3/chat-bi/backend/.venv/Scripts/python.exe -m pytest .codex-runtime/xiuxian-json-source-refresh/test_refresh_workbook.py -q`

Expected: FAIL，缺少 `("user", "userinfo")`。

- [ ] **Step 3: 实现分表来源字段选择并接入旧采样器**

```python
def resolve_source_columns(event_columns, user_columns):
    event = sorted({name for name in event_columns if name != "personal"})
    user = sorted({name for name in user_columns if name != "personal"})
    return [("event", name) for name in event] + [("user", name) for name in user]


sampler = load_sampler()
sampler.resolve_source_columns = resolve_source_columns
summary, stats = sampler.sample_database()
sampler.write_json_atomic(SUMMARY_PATH, summary)
```

- [ ] **Step 4: 运行测试并确认通过**

Run: `D:/AIWork3/chat-bi/backend/.venv/Scripts/python.exe -m pytest .codex-runtime/xiuxian-json-source-refresh/test_refresh_workbook.py -q`

Expected: PASS。

- [ ] **Step 5: 通过环境变量运行最新 28 天只读采样**

Run: `D:/AIWork3/chat-bi/backend/.venv/Scripts/python.exe .codex-runtime/xiuxian-json-source-refresh/refresh_workbook.py --sample-only`

Expected: 输出锚点、起止日期、选中字段数、JSON 来源字段数和叶子路径数；摘要不含 `personal`，且同一 `(来源表, 来源字段, JSON路径)` 唯一。

### Task 2: 原子更新六列表并完成验收

**Files:**
- Modify: `docs/xiuxian/tracking_dictionary_template_xiuxian_supplemented.xlsx`
- Modify temporary: `.codex-runtime/xiuxian-json-source-refresh/refresh_workbook.py`
- Create temporary: `.codex-runtime/xiuxian-json-source-refresh/validation-summary.json`

**Interfaces:**
- Consumes: Task 1 的 `sample-summary.json` 与当前工作簿。
- Produces: 六列、首列可见且可被平台导入的 `JSON字段解析` Sheet。

- [ ] **Step 1: 记录除目标 Sheet 外的工作簿指纹**

```python
def sheet_fingerprint(sheet):
    return {
        "title": sheet.title,
        "max_row": sheet.max_row,
        "max_column": sheet.max_column,
        "merged_ranges": sorted(str(item) for item in sheet.merged_cells.ranges),
        "values": tuple(tuple(cell.value for cell in row) for row in sheet.iter_rows()),
    }
```

- [ ] **Step 2: 构造六列行并保留/生成属性说明**

```python
HEADERS = ["来源表", "来源字段", "JSON路径", "生成字段名", "类型", "属性说明"]

rows = [
    [
        item["source_table"],
        item["source_field"],
        item["json_path"],
        item["generated_field_name"],
        item["inferred_type"],
        describe(item, existing_descriptions, descriptions_by_leaf),
    ]
    for item in summary["rows"]
]
```

保留旧表中 JSON 路径为空的确认行，并补写可验证的来源表；有效路径按 event、user、来源字段、JSON 路径稳定排序。

- [ ] **Step 3: 在临时副本中更新并原子替换目标工作簿**

先对现有 `JSON字段解析` 执行 `insert_cols(1)`，复用原有表头和数据样式；清空旧数据后写入六列和新行，设置 `A` 列宽度并确保 `column_dimensions["A"].hidden is not True`。保存到同目录临时文件，重新打开并通过全部断言后使用 `os.replace(...)` 替换目标文件。

- [ ] **Step 4: 验证工作簿结构和平台导入往返**

Run: `D:/AIWork3/chat-bi/backend/.venv/Scripts/python.exe .codex-runtime/xiuxian-json-source-refresh/refresh_workbook.py --verify`

Expected:

```text
workbook_validation=PASS
source_table_header_visible=true
personal_rows=0
other_sheet_fingerprints_unchanged=true
tracking_excel_import=PASS
```

- [ ] **Step 5: 渲染并检查目标 Sheet**

如果本机有 LibreOffice，使用无界面模式转 PDF/PNG，检查表头、列宽、冻结行、筛选范围和长路径可读性；如果不可用，则记录环境限制并执行 openpyxl 样式/尺寸断言及 Excel 可打开性验证。

- [ ] **Step 6: 检查、提交并推送**

```powershell
git diff --check
git status --short
git add docs/superpowers/plans/2026-07-15-xiuxian-json-source-table-workbook-refresh.md docs/xiuxian/tracking_dictionary_template_xiuxian_supplemented.xlsx
git commit -m "文档：刷新修仙 JSON 来源表字段"
git push origin dongjinchao/rls_1.0.0
```

