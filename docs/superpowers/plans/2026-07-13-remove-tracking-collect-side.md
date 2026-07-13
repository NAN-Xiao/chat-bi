# 移除事件采集端实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 从 tracking 数据字典、事件目录、前端元数据和 LLM 语义上下文中彻底移除采集端，同时允许历史 Excel 静默忽略该列。

**Architecture:** 使用统一 `_sanitize_event_name_mappings` 清理运行时和持久化 JSON，Excel 层停止导出和解析该值但保留旧表头识别，事件目录前后端删除对应字段。Alembic `143trackingcollectside` 负责清理现有 JSON 键，真实工作簿验收确保 163 个事件及 756 行参数内容不变。

**Tech Stack:** Python 3.11、FastAPI、SQLModel/SQLAlchemy、PostgreSQL JSONB、Alembic、pandas/xlsxwriter、openpyxl、Vue 3、TypeScript、esbuild、Node.js test runner、pytest。

## Global Constraints

- 新导出的“事件参数对照”固定为 9 列，不再出现“采集端”。
- 历史 Excel 中的“采集端”或 `collectside` 列允许导入，但值静默忽略，不进入扩展属性。
- tracking 配置读取、保存、事件目录 API、前端 SQL 构建器和 LLM 上下文均不得暴露 `collect_side` 或 `collectSide`。
- 不修改事件名称、事件显示名、事件标签、事件参数、事件分组或其他 tracking 字段。
- 正常 First Zombie 字典仍为 163 个事件、756 行事件参数；删除列后范围为 `A1:I756`。
- Alembic 迁移只清理 JSON 键，不改表结构；downgrade 不恢复被删除值。
- 实施和自动测试不直接执行共享系统库迁移。
- 所有新增注释、错误说明、文档和提交信息使用中文。

---

### Task 1: 后端事件映射清理与事件目录契约

**Files:**
- Create: `backend/tests/test_tracking_collect_side_removal.py`
- Modify: `backend/apps/system/crud/tracking_config.py`
- Modify: `backend/apps/system/schemas/tenant_schema.py`
- Modify: `backend/tests/test_tracking_event_catalog.py`

**Interfaces:**
- Produces: `_sanitize_event_name_mappings(value: Any) -> list[Any]`，删除每个事件映射对象顶层的 `collect_side` 和 `collectSide`，不修改输入对象。
- Changes: `_config_dto(...)` 和 `save_tracking_config(...)` 统一使用清理函数。
- Changes: `_project_event_name_mappings(...)` 先清理直接构造的 DTO，保证 LLM 上下文不依赖数据库读取路径。
- Changes: `TenantTrackingEventCatalogItem` 和 `build_tracking_event_catalog(...)` 不再包含采集端。

- [ ] **Step 1: 写事件映射清理失败测试**

```python
from apps.system.crud.tracking_config import _sanitize_event_name_mappings


def test_event_mapping_sanitizer_removes_collect_side_without_mutating_input() -> None:
    mappings = [
        {"event_name": "login", "collect_side": "client"},
        {"event_name": "pay", "collectSide": "server"},
        "plain_event",
    ]

    cleaned = _sanitize_event_name_mappings(mappings)

    assert cleaned == [
        {"event_name": "login"},
        {"event_name": "pay"},
        "plain_event",
    ]
    assert mappings[0]["collect_side"] == "client"
    assert mappings[1]["collectSide"] == "server"
```

- [ ] **Step 2: 写数据库 DTO 读取清理失败测试**

```python
from apps.system.crud.tracking_config import _config_dto
from apps.system.models.tenant import TenantTrackingConfigModel


def test_tracking_config_dto_hides_legacy_collect_side() -> None:
    row = TenantTrackingConfigModel(
        id=1001,
        tenant_id=2001,
        datasource_id=3,
        event_name_mappings=[
            {"event_name": "login", "collect_side": "client", "collectSide": "server"}
        ],
    )

    dto = _config_dto(row, tenant_id=2001, datasource_id=3)

    assert dto.event_name_mappings == [{"event_name": "login"}]
```

- [ ] **Step 3: 写直接 DTO 的 LLM 上下文清理失败测试**

```python
from apps.system.crud.tracking_config import build_tracking_prompt_context
from apps.system.schemas.tenant_schema import TenantTrackingConfigDTO


def test_tracking_prompt_hides_collect_side_from_direct_config() -> None:
    config = TenantTrackingConfigDTO(
        tenant_id=2001,
        datasource_id=3,
        enabled=True,
        event_name_mappings=[
            {"event_name": "login", "collect_side": "client", "collectSide": "server"}
        ],
    )

    context, _ = build_tracking_prompt_context(config)

    assert "collect_side" not in context
    assert "collectSide" not in context
```

- [ ] **Step 4: 修改事件目录测试，要求 API 契约不含采集端**

在 `backend/tests/test_tracking_event_catalog.py` 的登录事件输入中同时保留 `collect_side` 和 `collectSide`，增加：

```python
    event_payload = catalog.groups[0].events[0].model_dump()
    assert "collect_side" not in event_payload
    assert "collectSide" not in event_payload
```

- [ ] **Step 5: 运行测试并确认 RED**

Run:

```powershell
cd backend
.venv\Scripts\python.exe -m pytest `
  tests/test_tracking_collect_side_removal.py `
  tests/test_tracking_event_catalog.py -q
```

Expected: FAIL，提示 `_sanitize_event_name_mappings` 不存在，且事件目录仍包含 `collect_side`。

- [ ] **Step 6: 实现统一清理函数并接入读写与投影路径**

在 `backend/apps/system/crud/tracking_config.py` 增加：

```python
def _sanitize_event_name_mappings(value: Any) -> list[Any]:
    sanitized: list[Any] = []
    for item in _json_list(value):
        if not isinstance(item, dict):
            sanitized.append(copy.deepcopy(item))
            continue
        cleaned = copy.deepcopy(item)
        cleaned.pop("collect_side", None)
        cleaned.pop("collectSide", None)
        sanitized.append(cleaned)
    return sanitized
```

把 `_config_dto` 中的：

```python
event_name_mappings=_json_list(row.event_name_mappings),
```

替换为：

```python
event_name_mappings=_sanitize_event_name_mappings(row.event_name_mappings),
```

把 `save_tracking_config` 中的：

```python
config.event_name_mappings = _json_list(editor.event_name_mappings)
```

替换为：

```python
config.event_name_mappings = _sanitize_event_name_mappings(editor.event_name_mappings)
```

在 `_project_event_name_mappings` 开头增加：

```python
mappings = _sanitize_event_name_mappings(mappings)
```

这样直接构造的 DTO 也不会把采集端放入 LLM tracking prompt。

- [ ] **Step 7: 删除后端事件目录采集端字段**

从 `TenantTrackingEventCatalogItem` 删除：

```python
collect_side: str = ""
```

从 `build_tracking_event_catalog` 的 `TenantTrackingEventCatalogItem(...)` 构造参数中删除：

```python
collect_side=_plain_text(mapping.get("collect_side")),
```

- [ ] **Step 8: 运行测试并确认 GREEN**

Run:

```powershell
cd backend
.venv\Scripts\python.exe -m pytest `
  tests/test_tracking_collect_side_removal.py `
  tests/test_tracking_event_catalog.py `
  tests/test_tracking_context_projection.py -q
```

Expected: PASS；tracking context 投影测试证明输入 DTO 未被原地修改。

- [ ] **Step 9: 提交后端运行时清理**

```powershell
git add backend/apps/system/crud/tracking_config.py `
  backend/apps/system/schemas/tenant_schema.py `
  backend/tests/test_tracking_collect_side_removal.py `
  backend/tests/test_tracking_event_catalog.py
git commit -m "功能：移除事件采集端运行时字段"
```

---

### Task 2: Excel 导出移除与历史导入静默忽略

**Files:**
- Modify: `backend/apps/system/crud/tracking_excel.py`
- Modify: `backend/tests/test_tracking_excel.py`

**Interfaces:**
- Changes: `EVENT_PARAMETER_MAPPING_COLUMNS` 固定为 9 列。
- Preserves: `HEADER_ALIASES["collectside"]` 和 `HEADER_ALIASES["采集端"]`，只用于识别旧文件。
- Removes: Excel 解析、行构造和合并逻辑中的采集端值。

- [ ] **Step 1: 修改导出表头测试并确认新列顺序**

把 `test_tracking_excel_uses_physical_table_sheets_and_roundtrips_to_prompt_context` 的表头断言改为：

```python
assert _headers(workbook_bytes, "事件参数对照") == [
    "事件名（必填）",
    "事件显示名",
    "事件说明",
    "事件标签",
    "数据源字段",
    "属性名（必填）",
    "属性显示名",
    "属性类型（必填）",
    "属性说明",
]
```

- [ ] **Step 2: 增加历史 10 列 Excel 静默忽略测试**

```python
def test_legacy_collect_side_column_is_silently_ignored() -> None:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "事件参数对照"
    sheet.append([
        "事件名（必填）",
        "事件显示名",
        "事件说明",
        "事件标签",
        "采集端",
        "数据源字段",
        "属性名（必填）",
        "属性显示名",
        "属性类型（必填）",
        "属性说明",
    ])
    sheet.append([
        "login", "用户登录", "登录成功事件", "基础事件", "client",
        "ext", "serverId", "服务器ID", "文本", "服务器ID",
    ])
    output = BytesIO()
    workbook.save(output)

    parsed = parse_tracking_excel(
        output.getvalue(),
        TenantTrackingConfigDTO(tenant_id=2001, datasource_id=3, enabled=True),
    )

    event = parsed.editor.event_name_mappings[0]
    assert event["event_name"] == "login"
    assert "collect_side" not in event
    assert "collectSide" not in event
```

- [ ] **Step 3: 运行测试并确认 RED**

Run:

```powershell
cd backend
.venv\Scripts\python.exe -m pytest `
  tests/test_tracking_excel.py::test_tracking_excel_uses_physical_table_sheets_and_roundtrips_to_prompt_context `
  tests/test_tracking_excel.py::test_legacy_collect_side_column_is_silently_ignored -q
```

Expected: FAIL；导出仍包含“采集端”，旧文件仍把 `collect_side` 写入事件映射。

- [ ] **Step 4: 删除 Excel 输出列和业务行字段**

在 `backend/apps/system/crud/tracking_excel.py`：

- 从 `BUSINESS_COLUMNS` 和 `EVENT_PARAMETER_MAPPING_COLUMNS` 删除 `collect_side`。
- 从 `EXPORT_COLUMN_LABELS` 和 `BUSINESS_EXPORT_COLUMN_LABELS` 删除 `collect_side`。
- 保留 `HEADER_ALIASES` 中 `collectside/采集端 -> collect_side`，确保旧表头仍可识别且被 `KNOWN_IMPORT_COLUMNS` 排除在扩展属性之外。
- 删除所有导出行字典中的 `"collect_side": ...`。
- 删除 `_event_collect_side_from_mapping`。
- 将事件参数合并键改为：

```python
merge_columns = [
    "event_name",
    "event_display_name",
    "event_description",
    "event_category",
]
```

- [ ] **Step 5: 删除 Excel 解析赋值但保留旧列识别**

从事件值和事件参数映射解析中删除：

```python
"collect_side": _text(row.get("collect_side")),
```

不删除 `HEADER_ALIASES` 的旧名称映射。这样旧列会留在规范化行字典中，但没有消费者，也不会进入 `_extra_properties_from_row`。

- [ ] **Step 6: 更新现有采集端测试数据与断言**

对 `backend/tests/test_tracking_excel.py` 中仍用于新格式导出的 `collect_side` 输入和“采集端”表头断言进行删除。保留 Step 2 的单一历史兼容测试，集中证明旧列静默忽略。

- [ ] **Step 7: 运行 Excel 回归并确认 GREEN**

Run:

```powershell
cd backend
.venv\Scripts\python.exe -m pytest tests/test_tracking_excel.py -q
```

Expected: PASS；事件参数映射的事件、属性、合并和事件分组测试全部通过。

- [ ] **Step 8: 提交 Excel 变更**

```powershell
git add backend/apps/system/crud/tracking_excel.py backend/tests/test_tracking_excel.py
git commit -m "功能：从事件参数对照移除采集端"
```

---

### Task 3: 前端事件目录与 SQL 构建器清理

**Files:**
- Modify: `frontend/src/views/dashboard/common/dashboardBuilderMetadata.ts`
- Modify: `frontend/src/views/dashboard/common/dashboardBuilderMetadata.test.mjs`
- Modify: `frontend/src/views/dashboard/common/DashboardSqlEditor.vue`

**Interfaces:**
- Changes: `TrackingEventCatalogItem` 不含 `collect_side`。
- Changes: `SchemaFieldOption` 不含 `collectSide`。
- Preserves: 事件选择、事件参数选择、字段索引和 SQL 构建行为。

- [ ] **Step 1: 写前端事件目录失败测试**

在 `dashboardBuilderMetadata.test.mjs` 的 `ServerPayLog` 输入增加：

```javascript
collect_side: 'server',
collectSide: 'client',
```

并增加断言：

```javascript
assert.equal('collect_side' in catalog.groups[0].events[0], false)
assert.equal('collectSide' in catalog.groups[0].events[0], false)
```

- [ ] **Step 2: 运行测试并确认 RED**

Run:

```powershell
cd frontend
node src/views/dashboard/common/dashboardBuilderMetadata.test.mjs
```

Expected: FAIL，事件目录结果仍含 `collect_side`。

- [ ] **Step 3: 删除前端类型与映射字段**

在 `dashboardBuilderMetadata.ts`：

- 从 `TrackingEventCatalogItem` 删除 `collect_side: string`。
- 从事件构造对象删除：

```typescript
collect_side: plainText(mapping.collect_side || mapping.collectSide),
```

在 `DashboardSqlEditor.vue`：

- 从 `SchemaFieldOption` 删除 `collectSide?: string`。
- 从 tracking event option 构造对象删除：

```typescript
collectSide: event?.collect_side || event?.collectSide || '',
```

- [ ] **Step 4: 运行前端测试并确认 GREEN**

Run:

```powershell
cd frontend
node src/views/dashboard/common/dashboardBuilderMetadata.test.mjs
npm run build
```

Expected: metadata test 输出 `dashboard builder metadata tests passed`；Vue TypeScript 构建和 Vite build 退出码均为 0。

- [ ] **Step 5: 提交前端清理**

```powershell
git add frontend/src/views/dashboard/common/dashboardBuilderMetadata.ts `
  frontend/src/views/dashboard/common/dashboardBuilderMetadata.test.mjs `
  frontend/src/views/dashboard/common/DashboardSqlEditor.vue
git commit -m "功能：移除前端事件采集端元数据"
```

---

### Task 4: PostgreSQL JSON 清理迁移

**Files:**
- Create: `backend/alembic/versions/143_remove_tracking_collect_side.py`
- Modify: `backend/tests/test_tracking_collect_side_removal.py`

**Interfaces:**
- Produces: Alembic revision `143trackingcollectside`，`down_revision = "142trackinggroups"`。
- Changes: 从事件映射数组的对象元素删除顶层 `collect_side` 和 `collectSide`，保持数组顺序及非对象元素。

- [ ] **Step 1: 写迁移链和 SQL 结构失败测试**

```python
import importlib.util
from pathlib import Path


def test_collect_side_migration_cleans_json_and_follows_head() -> None:
    migration_path = (
        Path(__file__).parents[1]
        / "alembic"
        / "versions"
        / "143_remove_tracking_collect_side.py"
    )
    spec = importlib.util.spec_from_file_location("remove_tracking_collect_side", migration_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    assert module.revision == "143trackingcollectside"
    assert module.down_revision == "142trackinggroups"
    sql = str(module.CLEAN_EVENT_MAPPINGS_SQL)
    assert "WITH ORDINALITY" in sql
    assert "- 'collect_side'" in sql
    assert "- 'collectSide'" in sql
    assert "ORDER BY item_order" in sql
```

- [ ] **Step 2: 运行测试并确认 RED**

Run:

```powershell
cd backend
.venv\Scripts\python.exe -m pytest `
  tests/test_tracking_collect_side_removal.py::test_collect_side_migration_cleans_json_and_follows_head -q
```

Expected: FAIL，迁移文件不存在。

- [ ] **Step 3: 创建 143 数据迁移**

```python
"""移除事件映射中的采集端字段。"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "143trackingcollectside"
down_revision = "142trackinggroups"
branch_labels = None
depends_on = None


CLEAN_EVENT_MAPPINGS_SQL = sa.text(
    """
    UPDATE sys_tenant_tracking_config AS config
    SET event_name_mappings = (
        SELECT COALESCE(
            jsonb_agg(
                CASE
                    WHEN jsonb_typeof(item) = 'object'
                    THEN item - 'collect_side' - 'collectSide'
                    ELSE item
                END
                ORDER BY item_order
            ),
            '[]'::jsonb
        ) AS event_name_mappings
        FROM jsonb_array_elements(config.event_name_mappings)
            WITH ORDINALITY AS mapping(item, item_order)
    )
    WHERE jsonb_typeof(config.event_name_mappings) = 'array'
      AND config.event_name_mappings::text ~ '"collect_side"|"collectSide"'
    """
)


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "sys_tenant_tracking_config" not in inspector.get_table_names():
        return
    op.execute(CLEAN_EVENT_MAPPINGS_SQL)


def downgrade() -> None:
    pass
```

- [ ] **Step 4: 运行迁移测试和 head 检查**

Run:

```powershell
cd backend
.venv\Scripts\python.exe -m pytest tests/test_tracking_collect_side_removal.py -q
.venv\Scripts\python.exe -c "from alembic.command import heads; from alembic.config import Config; config=Config(); config.set_main_option('script_location', 'alembic'); heads(config)"
```

Expected: tests PASS；输出唯一 `143trackingcollectside (head)`。

- [ ] **Step 5: 提交迁移**

```powershell
git add backend/alembic/versions/143_remove_tracking_collect_side.py `
  backend/tests/test_tracking_collect_side_removal.py
git commit -m "迁移：清理事件采集端历史数据"
```

---

### Task 5: 文档、全量回归和真实工作簿验收

**Files:**
- Modify: `docs/generic_tracking_excel_template.md`
- Modify: `docs/tracking_event_parameter_mapping_excel_design.md`
- Verify: `C:/Users/elex/Downloads/tracking_dictionary_current.xlsx`
- Create: `outputs/tracking-collect-side-removal/tracking_dictionary_current_without_collect_side.xlsx`

**Interfaces:**
- Verifies: 新格式 9 列、旧格式静默忽略、事件字典内容不变、事件分组不受影响。
- Does not execute: 共享系统库 Alembic upgrade。

- [ ] **Step 1: 更新用户和设计文档**

在两个文档中删除采集端字段说明、导出映射和示例值。增加一条历史兼容说明：

```markdown
历史 Excel 中的“采集端”列仍可导入，但平台会忽略该列，后续导出不再包含它。
```

- [ ] **Step 2: 运行后端目标回归**

Run:

```powershell
cd backend
.venv\Scripts\python.exe -m pytest `
  tests/test_tracking_collect_side_removal.py `
  tests/test_tracking_excel.py `
  tests/test_tracking_event_catalog.py `
  tests/test_tracking_context_projection.py `
  tests/test_tracking_event_groups.py `
  tests/test_flam_first_zombie_tracking_dictionary_seed.py -q
```

Expected: 全部 PASS；允许仓库既有 Pydantic deprecation warnings，不得出现新 failure/error。

- [ ] **Step 3: 运行前端和静态验证**

Run:

```powershell
cd frontend
node src/views/dashboard/common/dashboardBuilderMetadata.test.mjs
npm run build

cd ..\backend
.venv\Scripts\python.exe -m compileall -q apps/system ..\tools
.venv\Scripts\python.exe -m ruff check `
  apps/system/crud/tracking_config.py `
  apps/system/crud/tracking_excel.py `
  apps/system/schemas/tenant_schema.py `
  alembic/versions/143_remove_tracking_collect_side.py `
  tests/test_tracking_collect_side_removal.py `
  tests/test_tracking_excel.py `
  tests/test_tracking_event_catalog.py
```

Expected: 所有命令退出码 0。若 Ruff 报告目标文件中的既有、与本次无关告警，记录基线并仅修复本次新增告警。

- [ ] **Step 4: 使用恢复后的 163 事件配置生成真实导出**

通过与 `/system/tracking-config/export` 相同的数据流读取租户 `7477202383789887488`、数据源 `3/flam`：

```python
physical_schema, _, datasource_id = _workspace_physical_schema(session, 7477202383789887488)
config = get_tracking_config(
    session,
    7477202383789887488,
    datasource_id,
    include_legacy=False,
)
output = tracking_config_excel(config, physical_schema=physical_schema)
```

把结果保存到：

```text
outputs/tracking-collect-side-removal/tracking_dictionary_current_without_collect_side.xlsx
```

- [ ] **Step 5: 对比事件内容并进行工作簿视觉验收**

使用产品解析器验证：

```python
assert restored.event_name_mappings == baseline.event_name_mappings
assert len(restored.event_name_mappings) == 163
assert restored.event_groups is None
```

使用 `@oai/artifact-tool` 检查并渲染：

```text
事件参数对照范围：A1:I756
事件分组范围：A1:G1
首事件：GVGBattleResult
首参数：allianceId
公式错误：0
```

视觉检查确认“数据源字段”位于 E 列，属性相关列依次左移且没有合并错位、截断或空白占位列。

- [ ] **Step 6: 检查差异和共享库边界**

Run:

```powershell
git diff --check
git status --short
```

确认：

- 代码和迁移已提交。
- 真实验证 Excel 不进入 Git 提交。
- 未执行 `alembic upgrade`，未修改共享系统库中的现有 JSON。
- 如需立即清理共享库，先使用 `tools/postgres-backup-local.ps1` 备份，再由用户单独确认执行 143 迁移。

- [ ] **Step 7: 提交文档**

```powershell
git add docs/generic_tracking_excel_template.md `
  docs/tracking_event_parameter_mapping_excel_design.md
git commit -m "文档：更新事件参数对照字段说明"
```

---

## 完成标准

- 新导出的“事件参数对照”不包含“采集端”。
- 旧 Excel 的采集端值被静默忽略且不进入扩展属性。
- 后端 API、前端元数据和 LLM tracking 上下文均不含采集端。
- 新写入和旧读取的事件映射都经过统一清理。
- Alembic 唯一 head 为 `143trackingcollectside`。
- 真实 First Zombie 导出保持 163 个事件、756 行参数，范围为 `A1:I756`。
- 事件分组行为保持不变。
