# 保留无属性埋点事件实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复 First Zombie 事件字典，使 `UserActive` 等没有打点属性的合法事件在初始化、清理和重复执行种子后仍被保留。

**Architecture:** 在 First Zombie 种子脚本中维护独立的默认事件条目，每个事件允许 `properties: []`。通过纯函数按事件名合并缺失项，并在数据库中只更新当前租户和数据源的 `event_name_mappings`；已有事件对象完全保留，事件分组只做引用校验。

**Tech Stack:** Python 3.11、psycopg 3、PostgreSQL JSONB、pytest

## Global Constraints

- 事件名是工作空间内独立业务标识，事件属性是可选子数据。
- 不从事件分组反向生成或覆盖事件字典。
- 不为无属性事件虚构属性。
- 不覆盖用户维护的事件说明、分类和属性。
- 数据修复只能作用于 First Zombie 当前 `TENANT_ID` 与 `DATASOURCE_ID`。

---

## 文件结构

- Modify: `tools/seed_flam_first_zombie_tracking_dictionary.py`：声明独立默认事件，提供纯合并函数，并执行租户/数据源范围内的补缺更新。
- Modify: `backend/tests/test_flam_first_zombie_tracking_dictionary_seed.py`：覆盖空属性事件、无覆盖合并、幂等性、分组引用和 SQL 范围。
- Reference: `docs/superpowers/specs/2026-07-13-preserve-propertyless-tracking-events-design.md`：验收边界，不在实现中修改。

### Task 1: 用回归测试定义无属性事件与合并语义

**Files:**
- Modify: `backend/tests/test_flam_first_zombie_tracking_dictionary_seed.py`
- Test: `backend/tests/test_flam_first_zombie_tracking_dictionary_seed.py`

**Interfaces:**
- Consumes: `tools.seed_flam_first_zombie_tracking_dictionary.EVENT_GROUPS`
- Produces: 对 `DEFAULT_EVENT_MAPPINGS: list[dict]` 和 `merge_missing_event_mappings(existing: list, defaults: list[dict] | None = None) -> tuple[list, int]` 的行为约束。

- [ ] **Step 1: 写入失败测试**

```python
def test_tracking_dictionary_keeps_events_without_properties() -> None:
    import seed_flam_first_zombie_tracking_dictionary as tracking

    events = {item["event_name"]: item for item in tracking.DEFAULT_EVENT_MAPPINGS}
    assert events["UserActive"]["properties"] == []
    assert events["UserRegister"]["properties"] == []


def test_tracking_dictionary_merges_only_missing_events() -> None:
    import seed_flam_first_zombie_tracking_dictionary as tracking

    existing = [
        {
            "event_name": "UserActive",
            "event_display_name": "用户维护的活跃事件",
            "properties": [{"property_name": "custom.value"}],
        }
    ]
    defaults = [
        {"event_name": "UserActive", "properties": []},
        {"event_name": "UserRegister", "properties": []},
    ]

    merged, inserted = tracking.merge_missing_event_mappings(existing, defaults)

    assert inserted == 1
    assert merged[0] == existing[0]
    assert merged[1] == {"event_name": "UserRegister", "properties": []}
    assert existing == [
        {
            "event_name": "UserActive",
            "event_display_name": "用户维护的活跃事件",
            "properties": [{"property_name": "custom.value"}],
        }
    ]


def test_tracking_dictionary_event_merge_is_idempotent() -> None:
    import seed_flam_first_zombie_tracking_dictionary as tracking

    first, first_inserted = tracking.merge_missing_event_mappings([], tracking.DEFAULT_EVENT_MAPPINGS)
    second, second_inserted = tracking.merge_missing_event_mappings(first, tracking.DEFAULT_EVENT_MAPPINGS)

    assert first_inserted == len(tracking.DEFAULT_EVENT_MAPPINGS)
    assert second_inserted == 0
    assert second == first
```

- [ ] **Step 2: 运行测试并确认按预期失败**

Run: `backend/.venv/Scripts/python.exe -m pytest backend/tests/test_flam_first_zombie_tracking_dictionary_seed.py -q`

Expected: FAIL，指出 `DEFAULT_EVENT_MAPPINGS` 或 `merge_missing_event_mappings` 尚不存在；不得是导入错误或测试环境错误。

- [ ] **Step 3: 提交测试红灯状态对应的工作内容时不单独提交**

红灯测试与 Task 2 的最小实现组成同一个可审查提交，避免主分支出现必然失败的中间提交。

### Task 2: 实现独立默认事件与范围内补缺更新

**Files:**
- Modify: `tools/seed_flam_first_zombie_tracking_dictionary.py`
- Modify: `backend/tests/test_flam_first_zombie_tracking_dictionary_seed.py`
- Test: `backend/tests/test_flam_first_zombie_tracking_dictionary_seed.py`

**Interfaces:**
- Consumes: 现有事件常量列表、`TENANT_ID`、`DATASOURCE_ID`、`sys_tenant_tracking_config.event_name_mappings`。
- Produces: `DEFAULT_EVENT_MAPPINGS`、`merge_missing_event_mappings(...)`、`ensure_default_event_mappings(cur, now: int) -> int`。

- [ ] **Step 1: 声明独立默认事件条目**

在所有事件常量定义之后、`EVENT_GROUPS` 之前加入：

```python
DEFAULT_EVENT_NAMES = list(
    dict.fromkeys(
        REGISTER_EVENTS
        + LOGIN_EVENTS
        + TRANSACTION_EVENTS
        + PAYMENT_PROCESS_EVENTS
        + ["CCU"]
        + ONBOARDING_EVENTS
        + ACTIVITY_EVENTS
        + EXPEDITION_EVENTS
        + ARMY_EVENTS
        + GOLD_EVENTS
        + BUILDING_EVENTS
        + TECH_EVENTS
        + HERO_EVENTS
    )
)

DEFAULT_EVENT_MAPPINGS = [
    {"event_name": event_name, "properties": []}
    for event_name in DEFAULT_EVENT_NAMES
]
```

将 `TRACKING_CONFIG["event_name_mappings"]` 改为 `DEFAULT_EVENT_MAPPINGS`。这只影响新配置插入；现有配置仍不能由 `ON CONFLICT` 覆盖。

- [ ] **Step 2: 实现无覆盖合并纯函数**

在 `validate_event_group_defaults` 前加入：

```python
def _event_names_from_mapping(item: object) -> set[str]:
    if not isinstance(item, dict):
        return set()
    names: set[str] = set()
    for key in ("event_name", "eventName", "name", "value"):
        value = str(item.get(key) or "").strip()
        if value:
            names.add(value)
    for value in item.get("events") or []:
        text = str(value or "").strip()
        if text:
            names.add(text)
    return names


def merge_missing_event_mappings(
    existing: list,
    defaults: list[dict] | None = None,
) -> tuple[list, int]:
    merged = json.loads(json.dumps(existing or [], ensure_ascii=False))
    known_events = {
        event_name
        for item in merged
        for event_name in _event_names_from_mapping(item)
    }
    inserted = 0
    for item in defaults if defaults is not None else DEFAULT_EVENT_MAPPINGS:
        event_names = _event_names_from_mapping(item)
        if not event_names or event_names <= known_events:
            continue
        merged.append(json.loads(json.dumps(item, ensure_ascii=False)))
        known_events.update(event_names)
        inserted += 1
    return merged, inserted
```

- [ ] **Step 3: 实现数据库范围内补缺**

在 `upsert_event_groups` 前加入：

```python
def ensure_default_event_mappings(cur, now: int) -> int:
    cur.execute(
        """
        SELECT event_name_mappings
        FROM public.sys_tenant_tracking_config
        WHERE tenant_id = %s AND datasource_id = %s
        FOR UPDATE
        """,
        (TENANT_ID, DATASOURCE_ID),
    )
    row = cur.fetchone()
    if row is None:
        raise RuntimeError("First Zombie 事件字典配置不存在。")
    merged, inserted = merge_missing_event_mappings(row[0] or [])
    if inserted:
        cur.execute(
            """
            UPDATE public.sys_tenant_tracking_config
            SET event_name_mappings = %s, update_by = %s, update_time = %s
            WHERE tenant_id = %s AND datasource_id = %s
            """,
            (Jsonb(merged), UPDATE_BY, now, TENANT_ID, DATASOURCE_ID),
        )
    return inserted
```

在 `main()` 中紧接 `upsert_config(cur, now)` 调用 `inserted_events = ensure_default_event_mappings(cur, now)`，并在最终 JSON 输出中加入 `"inserted_events": inserted_events`。

- [ ] **Step 4: 补充 SQL 范围与分组引用测试**

```python
def test_tracking_dictionary_default_groups_reference_existing_events() -> None:
    import seed_flam_first_zombie_tracking_dictionary as tracking

    tracking.validate_event_group_defaults(
        tracking.EVENT_GROUPS,
        tracking.DEFAULT_EVENT_MAPPINGS,
    )


def test_tracking_dictionary_event_repair_is_scoped() -> None:
    content = (ROOT / "tools" / "seed_flam_first_zombie_tracking_dictionary.py").read_text(
        encoding="utf-8"
    )

    assert "WHERE tenant_id = %s AND datasource_id = %s" in content
    assert "event_name_mappings = EXCLUDED.event_name_mappings" not in content
    assert "ensure_default_event_mappings(cur, now)" in content
```

- [ ] **Step 5: 运行定向测试并确认通过**

Run: `backend/.venv/Scripts/python.exe -m pytest backend/tests/test_flam_first_zombie_tracking_dictionary_seed.py -q`

Expected: PASS，所有该文件测试通过。

- [ ] **Step 6: 运行相邻事件字典测试**

Run: `backend/.venv/Scripts/python.exe -m pytest backend/tests/test_tracking_event_catalog.py backend/tests/test_tracking_event_groups.py backend/tests/test_tracking_collect_side_removal.py -q`

Expected: PASS，事件目录、事件分组和采集端字段清理测试均通过。

- [ ] **Step 7: 提交代码修复**

```bash
git add backend/tests/test_flam_first_zombie_tracking_dictionary_seed.py tools/seed_flam_first_zombie_tracking_dictionary.py
git commit -m "修复：保留无属性埋点事件"
```

### Task 3: 定向修复 First Zombie 数据并验证

**Files:**
- Modify: 无代码文件；只更新 `zhishu_bi.public.sys_tenant_tracking_config` 中 First Zombie 当前租户和数据源记录。
- Test: 通过只读 SQL 验证数据库状态。

**Interfaces:**
- Consumes: `ensure_default_event_mappings(cur, now)`、仓库根目录 `.env` 中的核心数据库配置。
- Produces: First Zombie 事件字典中恢复的缺失默认事件，现有事件元数据保持不变。

- [ ] **Step 1: 修复前读取并记录当前摘要**

使用 `backend/.venv/Scripts/python.exe` 和 `psycopg` 查询目标行，输出事件总数、`UserActive` 是否存在，以及现有事件映射 JSON 的 SHA-256；查询条件必须同时包含 `TENANT_ID` 和 `DATASOURCE_ID`。

- [ ] **Step 2: 在单个事务中执行定向补缺**

```python
import time
import psycopg
from core_system_db import core_system_db_config
from seed_flam_first_zombie_tracking_dictionary import ensure_default_event_mappings

with psycopg.connect(**core_system_db_config()) as conn:
    with conn.cursor() as cur:
        inserted = ensure_default_event_mappings(cur, int(time.time()))
    conn.commit()
print({"inserted_events": inserted})
```

从 `tools` 目录或将 `tools` 加入 `PYTHONPATH` 后执行，避免调用完整种子流程引发无关元数据更新。

- [ ] **Step 3: 验证 `UserActive` 与空属性语义**

查询目标 `event_name_mappings`，断言：

```python
user_active = next(item for item in mappings if item.get("event_name") == "UserActive")
assert user_active.get("properties") == []
```

同时验证事件分组 `active_user.event_names` 仍为 `["UserActive"]`，且所有默认分组引用均能在事件字典中找到。

- [ ] **Step 4: 再次执行补缺验证幂等性**

再次调用 `ensure_default_event_mappings`。

Expected: 输出 `{"inserted_events": 0}`，目标映射 JSON 的 SHA-256 与第一次修复后相同。

- [ ] **Step 5: 执行最终验证**

Run: `backend/.venv/Scripts/python.exe -m pytest backend/tests/test_flam_first_zombie_tracking_dictionary_seed.py backend/tests/test_tracking_event_catalog.py backend/tests/test_tracking_event_groups.py backend/tests/test_tracking_collect_side_removal.py -q`

Expected: PASS，且数据库只读核验确认 `UserActive` 存在、属性为空、分组引用有效。
