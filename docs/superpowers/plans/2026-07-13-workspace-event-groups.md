# 工作空间事件分组实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 新增按工作空间和当前绑定数据源隔离的事件分组配置，支持独立 Excel 导入导出、语义上下文读取，并阻止 First Zombie 种子脚本再次覆盖完整事件参数字典。

**Architecture:** 使用独立 `sys_tenant_tracking_event_group` 表保存一组有序事件名，聚合进 tracking DTO 但不进入 `sys_tenant_tracking_config.event_name_mappings`。Excel 解析通过 `event_groups=None` 表示不处理，通过非空列表表示权威替换；保存前统一校验最终事件字典，语义上下文只注入当前数据源启用分组。

**Tech Stack:** Python 3.11、FastAPI、SQLModel/SQLAlchemy、PostgreSQL JSONB、Alembic、pandas/xlsxwriter、openpyxl、pytest。

## Global Constraints

- “事件参数对照”sheet 的表头、内容、参数展开和合并规则保持不变。
- “事件分组”sheet 缺失、只有表头或其余行全空时不得修改已有分组。
- 任一非空分组行校验失败时整个导入失败，不允许部分保存或静默跳过。
- 事件分组必须同时按 `tenant_id` 和 `datasource_id` 隔离。
- 普通 First Zombie seed 不得覆盖用户维护的事件字典或同名事件分组。
- 首期不增加可视化事件分组编辑界面和手动看板整组选择控件。
- 所有新增代码注释、错误信息、提交信息使用中文。

---

### Task 1: 事件分组模型、迁移与 CRUD

**Files:**
- Create: `backend/alembic/versions/142_tracking_event_groups.py`
- Create: `backend/tests/test_tracking_event_groups.py`
- Modify: `backend/apps/system/models/tenant.py`
- Modify: `backend/apps/system/schemas/tenant_schema.py`
- Modify: `backend/apps/system/crud/tracking_config.py`

**Interfaces:**
- Produces: `TenantTrackingEventGroupModel`、`TenantTrackingEventGroupBase`、`TenantTrackingEventGroupDTO`。
- Produces: `TenantTrackingConfigEditor.event_groups: list[TenantTrackingEventGroupBase] | None`；`None` 表示保留现有分组。
- Produces: `TenantTrackingConfigDTO.event_groups: list[TenantTrackingEventGroupDTO]`。
- Produces: `validate_tracking_event_groups(event_groups, event_name_mappings) -> None`。

- [ ] **Step 1: 写 DTO 和校验失败测试**

```python
def test_event_group_rejects_unknown_event() -> None:
    groups = [TenantTrackingEventGroupBase(
        group_key="payment_process",
        group_name="支付流程事件",
        event_names=["PayFinish2"],
    )]
    with pytest.raises(ValueError, match="PayFinish2"):
        validate_tracking_event_groups(groups, [{"event_name": "PayFinish"}])


def test_editor_omitted_event_groups_means_preserve() -> None:
    editor = TenantTrackingConfigEditor()
    assert editor.event_groups is None
```

- [ ] **Step 2: 运行测试并确认 RED**

Run: `cd backend; .venv/Scripts/python.exe -m pytest tests/test_tracking_event_groups.py -q`

Expected: FAIL，提示 DTO 或校验函数不存在。

- [ ] **Step 3: 实现 DTO、模型和校验函数**

```python
class TenantTrackingEventGroupBase(BaseModel):
    group_key: str = Field(pattern=r"^[a-z][a-z0-9_]{1,127}$")
    group_name: str = Field(min_length=1, max_length=255)
    description: Optional[str] = Field(default=None, max_length=4000)
    event_names: list[str] = Field(default_factory=list)
    sort_order: int = 0
    enabled: bool = True


class TenantTrackingEventGroupModel(SnowflakeBase, table=True):
    __tablename__ = "sys_tenant_tracking_event_group"
    # 唯一约束：(tenant_id, datasource_id, group_key)
```

`validate_tracking_event_groups` 从 `event_name`、`eventName`、`name`、`value` 和 `events[]` 收集最终事件集合，拒绝空成员、组内重复成员和未知事件。

- [ ] **Step 4: 增加 Alembic 迁移**

迁移 revision 使用 `142trackinggroups`，`down_revision = "141trackingextra"`，创建表、唯一约束和 `(tenant_id, datasource_id)` 索引；downgrade 仅删除新表。

- [ ] **Step 5: 实现读取与条件替换保存**

`get_tracking_config` 查询当前租户/数据源分组并填充 DTO。`save_tracking_config` 在 `editor.event_groups is None` 或空列表时保留现有分组并校验其引用，在非空列表时删除当前范围记录后写入新记录；所有校验在任何删除前完成，原有一次 `session.commit()` 保证原子提交。

- [ ] **Step 6: 运行目标测试并确认 GREEN**

Run: `cd backend; .venv/Scripts/python.exe -m pytest tests/test_tracking_event_groups.py -q`

Expected: PASS。

- [ ] **Step 7: 提交**

```bash
git add backend/alembic/versions/142_tracking_event_groups.py backend/apps/system/models/tenant.py backend/apps/system/schemas/tenant_schema.py backend/apps/system/crud/tracking_config.py backend/tests/test_tracking_event_groups.py
git commit -m "功能：新增工作空间事件分组存储"
```

### Task 2: 事件分组 Excel 导入导出

**Files:**
- Modify: `backend/apps/system/crud/tracking_excel.py`
- Modify: `backend/apps/system/api/tracking_config.py`
- Modify: `backend/apps/system/schemas/tenant_schema.py`
- Modify: `backend/tests/test_tracking_excel.py`

**Interfaces:**
- Consumes: `TenantTrackingConfigDTO.event_groups` 和 `TenantTrackingConfigEditor.event_groups`。
- Produces: 固定 sheet `事件分组`，列为 `group_key/group_name/description/sort_order/event_name/event_order/enabled`。
- Produces: `TenantTrackingImportSummary.event_group_count`。

- [ ] **Step 1: 写导出与空 sheet 保留测试**

```python
def test_event_groups_export_as_independent_sheet() -> None:
    config = _tracking_config().model_copy(update={"event_groups": [
        TenantTrackingEventGroupDTO(
            tenant_id=2001,
            group_key="payment_process",
            group_name="支付流程事件",
            event_names=["pay_success", "refund_success"],
            sort_order=10,
        )
    ]})
    workbook_bytes = tracking_config_excel(config, physical_schema=_physical_schema()).getvalue()
    assert _headers(workbook_bytes, "事件分组") == [
        "分组标识（必填）", "分组名称（必填）", "分组说明", "分组排序",
        "事件名（必填）", "事件排序", "启用",
    ]


def test_empty_event_group_sheet_preserves_existing_groups() -> None:
    parsed = parse_tracking_excel(workbook_with_header_only_group_sheet(), _tracking_config())
    assert parsed.editor.event_groups is None
```

- [ ] **Step 2: 运行测试并确认 RED**

Run: `cd backend; .venv/Scripts/python.exe -m pytest tests/test_tracking_excel.py -q -k "event_group"`

Expected: FAIL，提示 sheet 或 DTO 字段不存在。

- [ ] **Step 3: 实现导出常量和行展开**

增加 `EVENT_GROUP_SHEET = "事件分组"`、固定列和中文表头映射。每个事件输出完整分组字段，不合并单元格；无分组时仍输出表头。sheet 顺序放在“事件参数对照”之后、物理表 sheet 之前。

- [ ] **Step 4: 实现严格解析与最终事件校验**

解析规则：

```python
if EVENT_GROUP_SHEET not in excel.sheet_names:
    imported.event_groups = None
elif not rows:
    imported.event_groups = None
else:
    imported.event_groups = _parse_event_group_sheet(rows)
```

按行校验完整字段；同组元数据冲突、重复成员、非法排序/布尔值均抛出包含 sheet 和 Excel 行号的 `ValueError`。完成所有 sheet 解析及事件去重后，调用 `validate_tracking_event_groups` 校验最终事件集合。

- [ ] **Step 5: 实现悬空引用保护和 API 400**

`save_tracking_config` 在保留旧分组时也校验新的 `event_name_mappings`。Excel 导入和普通配置更新捕获 `ValueError`、回滚 session，并返回 HTTP 400 的明确中文错误。

- [ ] **Step 6: 补齐替换、多分组和错误测试**

覆盖：有效 sheet 权威替换、同一事件属于多组、重复成员失败、未知事件失败、空字段失败、同组名称冲突失败、删除被旧分组引用事件失败，以及“事件参数对照”既有断言保持不变。

- [ ] **Step 7: 运行目标测试并确认 GREEN**

Run: `cd backend; .venv/Scripts/python.exe -m pytest tests/test_tracking_excel.py tests/test_tracking_event_groups.py -q`

Expected: PASS。

- [ ] **Step 8: 提交**

```bash
git add backend/apps/system/crud/tracking_excel.py backend/apps/system/api/tracking_config.py backend/apps/system/schemas/tenant_schema.py backend/tests/test_tracking_excel.py backend/tests/test_tracking_event_groups.py
git commit -m "功能：支持事件分组 Excel 维护"
```

### Task 3: 事件分组语义上下文

**Files:**
- Modify: `backend/apps/system/crud/tracking_config.py`
- Modify: `backend/tests/test_tracking_context_projection.py`

**Interfaces:**
- Consumes: `TenantTrackingConfigDTO.event_groups`。
- Produces: `<Workspace-Tracking-Rules>` 中独立 `## 事件分组` JSON 区块。

- [ ] **Step 1: 写启用分组上下文测试**

```python
def test_tracking_prompt_includes_only_enabled_event_groups() -> None:
    config = _tracking_config().model_copy(update={"event_groups": [
        TenantTrackingEventGroupDTO(
            tenant_id=1,
            group_key="payment_process",
            group_name="支付流程事件",
            event_names=["pay_success"],
            enabled=True,
        ),
        TenantTrackingEventGroupDTO(
            tenant_id=1,
            group_key="disabled_group",
            group_name="停用分组",
            event_names=["login"],
            enabled=False,
        ),
    ]})
    context, _ = build_tracking_prompt_context(config)
    assert "payment_process" in context
    assert "disabled_group" not in context
```

- [ ] **Step 2: 运行测试并确认 RED**

Run: `cd backend; .venv/Scripts/python.exe -m pytest tests/test_tracking_context_projection.py -q -k "event_group"`

Expected: FAIL，启用分组尚未进入上下文。

- [ ] **Step 3: 实现独立结构化上下文**

按 `sort_order/group_key` 排序，只序列化启用分组的 `group_key/group_name/description/event_names`。该区块独立于“事件名映射”，不得把成员写回或合并到 `event_name_mappings`。

- [ ] **Step 4: 运行上下文和调用链回归**

Run: `cd backend; .venv/Scripts/python.exe -m pytest tests/test_tracking_context_projection.py tests/test_tracking_excel.py ../tests/test_custom_prompt_agent_permissions.py -q`

Expected: PASS。

- [ ] **Step 5: 提交**

```bash
git add backend/apps/system/crud/tracking_config.py backend/tests/test_tracking_context_projection.py
git commit -m "功能：向语义上下文注入事件分组"
```

### Task 4: First Zombie 种子防覆盖

**Files:**
- Modify: `tools/seed_flam_first_zombie_tracking_dictionary.py`
- Modify: `backend/tests/test_flam_first_zombie_tracking_dictionary_seed.py`

**Interfaces:**
- Produces: 独立 `EVENT_GROUPS` 常量。
- Produces: `upsert_event_groups(cur, now)`，仅在显式 `--seed-event-groups` 时校验并创建缺失分组。
- Changes: `upsert_config` 冲突更新不再写 `event_name_mappings`。

- [ ] **Step 1: 写分组分离和防覆盖测试**

```python
def test_tracking_seed_keeps_event_dictionary_separate_from_groups() -> None:
    import seed_flam_first_zombie_tracking_dictionary as tracking
    groups = {item["group_key"]: item for item in tracking.EVENT_GROUPS}
    assert tracking.TRACKING_CONFIG["event_name_mappings"] == []
    assert groups["payment_transaction"]["event_names"] == ["ServerPayLog"]
    assert "ServerPayLog" not in groups["payment_process_event"]["event_names"]


def test_tracking_seed_does_not_overwrite_existing_group_or_event_dictionary() -> None:
    content = seed_script.read_text(encoding="utf-8")
    assert "event_name_mappings = EXCLUDED.event_name_mappings" not in content
    assert "ON CONFLICT (tenant_id, datasource_id, group_key) DO NOTHING" in content
```

- [ ] **Step 2: 运行测试并确认 RED**

Run: `cd backend; .venv/Scripts/python.exe -m pytest tests/test_flam_first_zombie_tracking_dictionary_seed.py -q`

Expected: FAIL，分析集合仍位于 `event_name_mappings`。

- [ ] **Step 3: 分离常量并修改 SQL**

把 13 个分析集合转换为 `EVENT_GROUPS`。`TRACKING_CONFIG["event_name_mappings"]` 设为空，仅用于首次创建主配置；`ON CONFLICT` 更新列表中移除 `event_name_mappings`。事件字段的 `value_mappings` 不再引用分析集合，且冲突更新不得用空列表覆盖用户值。

- [ ] **Step 4: 增加缺失分组幂等插入**

`upsert_event_groups` 先读取当前 `event_name_mappings`，验证全部默认成员存在，再按当前 `TENANT_ID/DATASOURCE_ID` 插入 JSONB 事件数组，冲突时 `DO NOTHING`。`main` 默认不调用，只有 `--seed-event-groups` 显式启用；字典缺少成员或数据库尚未执行 142 迁移时给出明确错误，不自动删减成员或退回旧写法。

- [ ] **Step 5: 运行种子回归并确认 GREEN**

Run: `cd backend; .venv/Scripts/python.exe -m pytest tests/test_flam_first_zombie_tracking_dictionary_seed.py -q`

Expected: PASS。

- [ ] **Step 6: 提交**

```bash
git add tools/seed_flam_first_zombie_tracking_dictionary.py backend/tests/test_flam_first_zombie_tracking_dictionary_seed.py
git commit -m "修复：隔离 First Zombie 事件字典与分组"
```

### Task 5: 全量验证与迁移运行说明

**Files:**
- Modify: `docs/superpowers/specs/2026-07-13-workspace-event-groups-design.md`（仅当实现与设计需要同步时）

**Interfaces:**
- Verifies: 目标功能、现有 tracking 回归、迁移链和代码格式。

- [ ] **Step 1: 运行目标测试集合**

Run:

```powershell
cd backend
.venv\Scripts\python.exe -m pytest `
  tests/test_tracking_event_groups.py `
  tests/test_tracking_excel.py `
  tests/test_tracking_context_projection.py `
  tests/test_flam_first_zombie_tracking_dictionary_seed.py `
  ../tests/test_custom_prompt_agent_permissions.py -q
```

Expected: 全部 PASS，无 warning/error。

- [ ] **Step 2: 验证迁移链和静态编译**

Run:

```powershell
cd backend
.venv\Scripts\python.exe -m compileall apps/system ../tools
.venv\Scripts\python.exe -m alembic heads
```

Expected: 编译成功；唯一 head 为 `142trackinggroups`。

- [ ] **Step 3: 检查差异和设计验收项**

Run: `git diff --check; git status --short`

逐项确认：事件参数 sheet 未改变、空分组 sheet 不处理、非法引用阻止保存、语义上下文只含启用分组、种子不覆盖。

- [ ] **Step 4: 记录受控数据恢复步骤但不直接执行共享库变更**

运行时顺序必须是：先用 `tools/postgres-backup-local.ps1` 备份；再执行 Alembic 142；导入业务确认的正常 `tracking_dictionary_current.xlsx` 恢复完整事件字典；事件分组通过 Excel 维护。只有业务确认默认分组中的每个事件都已进入权威字典后，才可显式运行 `--seed-event-groups` 创建缺失分组。实现会交付代码和迁移，不在自动测试阶段直接修改 `10.1.5.28` 共享系统库。

- [ ] **Step 5: 最终提交（仅设计文档因实现变化而同步时）**

```bash
git add docs/superpowers/specs/2026-07-13-workspace-event-groups-design.md
git commit -m "测试：验证工作空间事件分组配置"
```
