# 修仙 0715 事件 JSON 属性展开 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 对 `xtxdj.event.personal` 做受限真实采样，将 `tracking_dictionary_0715.xlsx` 中的 JSON 对象和数组事件属性展开为带完整父前缀的叶子路径，并生成不覆盖原文件的新工作簿。

**Architecture:** 一个临时 Python 模块负责候选父属性识别、分事件采样、递归 JSON 展开和工作簿重写；测试模块覆盖纯函数和行替换边界。当前参考字典只用于恢复平台往返时丢失的旧父路径映射，新增和更新的叶子路径全部来自本次数据库样本。

**Tech Stack:** Python 3、PyMySQL、openpyxl、pytest、LibreOffice（若本机可用）。

## Global Constraints

- 输入固定为 `D:/AIWork3/djinchao/chat-bi/docs/xiuxian/tracking_dictionary_0715.xlsx`。
- 输出固定为 `D:/AIWork3/djinchao/chat-bi/docs/xiuxian/tracking_dictionary_0715_json_expanded.xlsx`，不得覆盖输入文件。
- 数据库只读访问 `xtxdj.event`、`xtxdj.user`，采样窗口为最大业务日期向前 28 个业务日。
- 每个候选事件独立设置样本上限，避免高频事件挤占低频事件样本。
- 对象路径使用 `parent.child`，对象数组路径使用 `parent[].child`，标量数组使用 `parent[]`。
- 只将真实样本中的标量叶子写入字典；未命中对象保留父行并写明未采样。
- 数据库凭据只通过进程环境变量传入，不写入脚本、摘要、工作簿或日志。
- 只修改输出文件的“事件参数对照”Sheet，其他 Sheet 保持不变。

---

### Task 1: JSON 展开与事件参数行转换

**Files:**
- Create temporary: `.codex-runtime/xiuxian-tracking-0715-json-expansion/expand_tracking_dictionary.py`
- Create temporary: `.codex-runtime/xiuxian-tracking-0715-json-expansion/test_expand_tracking_dictionary.py`

**Interfaces:**
- Produces: `flatten_json(value: object, path: str) -> list[Leaf]`
- Produces: `merge_leaf_samples(parent: str, samples: list[object]) -> list[Leaf]`
- Produces: `load_event_rows(path: Path) -> list[EventRow]`
- Produces: `build_legacy_path_map(reference_path: Path) -> dict[tuple[str, str], str]`
- Produces: `expand_rows(rows: list[EventRow], sampled: dict[Pair, SampledObject], legacy_map: dict) -> list[EventRow]`

- [ ] **Step 1: 编写 JSON 递归展开失败测试**

```python
def test_flatten_json_keeps_parent_and_array_markers():
    assert flatten_json({"WORLD_FU_MU": 5}, "ed_change") == [
        Leaf("ed_change.WORLD_FU_MU", "数值")
    ]
    assert flatten_json([{"itemId": 1}], "ed_drawResult") == [
        Leaf("ed_drawResult[].itemId", "数值")
    ]
    assert flatten_json(["a", "b"], "ed_productIds") == [
        Leaf("ed_productIds[]", "文本")
    ]
```

- [ ] **Step 2: 编写二次 JSON 和类型合并失败测试**

```python
def test_merge_leaf_samples_parses_json_strings_and_merges_numbers():
    leaves = merge_leaf_samples("ed_value", ['{"n": 1}', {"n": 1.5}])
    assert leaves == [Leaf("ed_value.n", "数值")]
```

- [ ] **Step 3: 编写旧路径恢复与 ResourceChange 替换失败测试**

```python
def test_expand_rows_replaces_legacy_flat_children_with_full_paths():
    rows = fixture_rows([
        ("ResourceChange", "WORLD_FU_MU", "数值", "参数说明：资源变化量；子字段含义：世界资源：扶木"),
    ])
    sampled = {
        ("ResourceChange", "ed_change"): SampledObject(
            sample_count=10,
            leaves=[Leaf("ed_change.WORLD_FU_MU", "数值")],
        )
    }
    legacy = {("ResourceChange", "WORLD_FU_MU"): "ed_change.WORLD_FU_MU"}
    output = expand_rows(rows, sampled, legacy)
    assert property_names(output, "ResourceChange") == ["ed_change.WORLD_FU_MU"]
```

- [ ] **Step 4: 运行测试确认失败**

Run: `D:/AIWork3/chat-bi/backend/.venv/Scripts/python.exe -m pytest .codex-runtime/xiuxian-tracking-0715-json-expansion/test_expand_tracking_dictionary.py -q`

Expected: FAIL，模块或目标函数尚不存在。

- [ ] **Step 5: 实现最小纯函数**

```python
@dataclass(frozen=True, order=True)
class Leaf:
    path: str
    field_type: str


def parse_nested_json(value):
    if not isinstance(value, str) or not value.strip().startswith(("{", "[")):
        return value
    try:
        return json.loads(value)
    except ValueError:
        return value


def flatten_json(value, path):
    value = parse_nested_json(value)
    if isinstance(value, dict):
        return [leaf for key, child in value.items() for leaf in flatten_json(child, f"{path}.{key}")]
    if isinstance(value, list):
        leaves = [leaf for child in value for leaf in flatten_json(child, f"{path}[]")]
        return unique_leaves(leaves) or [Leaf(f"{path}[]", "对象组")]
    return [Leaf(path, scalar_type(value))]
```

- [ ] **Step 6: 实现参考路径映射和行替换**

参考字典固定读取 `docs/xiuxian/tracking_dictionary_template_xiuxian_supplemented.xlsx`。仅收集说明含“子字段含义”的行，并以 `(事件名, 当前叶子名)` 映射到完整路径；替换时只移除父行、同一父路径的完整叶子行，或说明明确为旧子字段且命中映射的平铺行。

```python
def root_path(path):
    return re.split(r"\.|\[\]", path, maxsplit=1)[0]


def is_replaceable(row, event_name, parent, legacy_map):
    if row.event_name != event_name:
        return False
    if row.property_name == parent or row.property_name.startswith((f"{parent}.", f"{parent}[]")):
        return True
    restored = legacy_map.get((event_name, row.property_name))
    return "子字段含义" in row.description and restored and root_path(restored) == parent
```

- [ ] **Step 7: 运行纯函数测试确认通过**

Run: `D:/AIWork3/chat-bi/backend/.venv/Scripts/python.exe -m pytest .codex-runtime/xiuxian-tracking-0715-json-expansion/test_expand_tracking_dictionary.py -q`

Expected: PASS。

### Task 2: 分事件采样、生成工作簿并验收

**Files:**
- Modify temporary: `.codex-runtime/xiuxian-tracking-0715-json-expansion/expand_tracking_dictionary.py`
- Create temporary: `.codex-runtime/xiuxian-tracking-0715-json-expansion/sample-summary.json`
- Create temporary: `.codex-runtime/xiuxian-tracking-0715-json-expansion/validation-summary.json`
- Create: `D:/AIWork3/djinchao/chat-bi/docs/xiuxian/tracking_dictionary_0715_json_expanded.xlsx`

**Interfaces:**
- Consumes: Task 1 的 `Leaf`、`expand_rows(...)` 和参考路径映射。
- Produces: `sample_database(candidates: set[Pair]) -> SamplingResult`
- Produces: `write_output(input_path: Path, output_path: Path, rows: list[EventRow]) -> None`
- Produces: `validate_output(input_path: Path, output_path: Path, summary: SamplingResult) -> dict`

- [ ] **Step 1: 编写候选识别和采样边界测试**

候选父属性由两部分组成：目标字典中全部 846 条 `(事件名, 属性名)`，以及参考路径映射中的父路径。测试必须断言 `("ResourceChange", "ed_change")`、`("ResourceChange", "ed_stock")`、当前 31 条 `对象组` 父属性和普通标量属性均进入采样候选；普通标量属性没有对象样本时不得改变原行。

- [ ] **Step 2: 实现分事件只读采样**

```python
cursor.execute("SELECT MAX(dt) FROM user")
anchor_dt = int(cursor.fetchone()[0])
start_dt = int((datetime.strptime(str(anchor_dt), "%Y%m%d").date() - timedelta(days=27)).strftime("%Y%m%d"))
for event_name in sorted(events):
    cursor.execute(
        "SELECT personal FROM event WHERE dt BETWEEN %s AND %s AND event=%s LIMIT %s",
        (start_dt, anchor_dt, event_name, per_event_limit),
    )
```

每个事件查询一次，并同时检查该事件的全部候选属性；样本值是对象、数组或可再次解析为对象/数组时才生成叶子。标量样本不进入替换集合。摘要记录事件、父属性、对象样本命中数、叶子路径和类型，不记录原始值。

- [ ] **Step 3: 运行采样并检查摘要**

Run: 设置 `XIUXIAN_DB_HOST`、`XIUXIAN_DB_PORT`、`XIUXIAN_DB_USER`、`XIUXIAN_DB_PASSWORD`、`XIUXIAN_DB_NAME` 后执行：

`D:/AIWork3/chat-bi/backend/.venv/Scripts/python.exe .codex-runtime/xiuxian-tracking-0715-json-expansion/expand_tracking_dictionary.py --sample-only`

Expected: 摘要包含动态锚点和最近 28 个业务日；`ResourceChange.ed_change` 至少包含一个 `ed_change.*` 叶子；摘要文本中不包含密码、UID 或完整 `personal`。

- [ ] **Step 4: 原子生成输出工作簿**

加载输入工作簿并记录 SHA-256。对“事件参数对照”先在内存中构造新行，再复制来源行样式、行高、冻结窗格、筛选和表格范围；保存为同目录临时文件，重新打开并完成断言后使用 `os.replace(temp_path, output_path)`。

- [ ] **Step 5: 验证内容和结构**

`validate_output(...)` 必须断言：

```python
assert sha256(input_path) == original_input_hash
assert output.sheetnames == input_workbook.sheetnames
assert fingerprints_except_event_sheet(input_workbook) == fingerprints_except_event_sheet(output)
assert "ed_change.WORLD_FU_MU" in resource_change_properties
assert "WORLD_FU_MU" not in resource_change_properties
assert all(item.path.startswith(f"{item.parent}.") or item.path.startswith(f"{item.parent}[]") for item in sampled_leaves)
```

同时扫描单元格中的 `#REF!`、`#DIV/0!`、`#VALUE!`、`#NAME?` 和 `#N/A`。

- [ ] **Step 6: 完成视觉检查**

若 `soffice` 可用，将输出文件无界面导出为 PDF/PNG，检查“事件参数对照”表头、长 JSON 路径、换行、列宽和事件分组；若不可用，执行列宽、行高、冻结行、筛选范围、表格范围和代表性样式断言，并在验收摘要中记录环境限制。

- [ ] **Step 7: 运行全部测试和最终验证**

Run:

`D:/AIWork3/chat-bi/backend/.venv/Scripts/python.exe -m pytest .codex-runtime/xiuxian-tracking-0715-json-expansion/test_expand_tracking_dictionary.py -q`

`D:/AIWork3/chat-bi/backend/.venv/Scripts/python.exe .codex-runtime/xiuxian-tracking-0715-json-expansion/expand_tracking_dictionary.py --verify`

Expected: 测试 PASS，`workbook_validation=PASS`，原文件哈希未变化，最终文件存在且可重新打开。
