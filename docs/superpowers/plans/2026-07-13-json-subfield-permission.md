# JSON 子字段级权限实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在不改变现有权限页面展示的前提下，为物理 JSON 容器增加工作空间级子路径权限，并修复字段规则导致合法历史查询被整体误封的问题。

**Architecture:** 复用 `sys_tenant_tracking_field` 中的 `source_field/json_path` 作为 JSON 子字段身份，在现有 `ds_permission.permissions` 中保存服务端规范化后的路径。抽取共享 SQLGlot JSON 访问解析器，让 SQL 生成校验和运行时权限校验使用同一套跨方言路径识别；表/字段/JSON 路径由原 SQL精确重校验，只有行级权限触发历史数据实时刷新。

**Tech Stack:** Python 3.11、FastAPI、SQLAlchemy/SQLModel、SQLGlot、pytest、Vue 3、TypeScript、Node.js

## Global Constraints

- 核心权限逻辑必须保持业务域和数据源无关，不硬编码 `personal.money`、ARPU、游戏字段或数据源 ID。
- 工作空间 JSON 字段身份只来自当前工作空间、当前数据源和当前表的 `sys_tenant_tracking_field`。
- 权限页面继续使用当前扁平列表，不修改布局、开关语义、显示内容或文案。
- 禁止路径与访问路径存在父子关系时拒绝；同级无交集路径允许。
- 禁止任意 JSON 子路径后，直接读取容器、`SELECT *`、动态路径或无法可靠解析的路径必须安全失败。
- 普通用户只看到统一的“没有查看权限”，具体路径只写服务端审计日志。
- 不新增数据库表、不执行 schema 迁移、不猜测或迁移旧权限 JSON。
- 现有物理字段、表级权限和行级权限必须保持兼容。
- Git 提交信息使用中文。

---

## 文件结构

- Create: `backend/common/sql_json_paths.py`：跨方言 JSON 路径规范化、结构比较和 SQLGlot AST 提取。
- Modify: `backend/apps/dashboard/crud/ai_sql_generator.py`：改用共享 JSON 路径解析器，删除重复的私有解析实现。
- Modify: `backend/apps/datasource/api/permission.py`：在保存规则前按工作空间元数据规范化字段权限条目。
- Create: `backend/apps/datasource/crud/permission_fields.py`：校验物理字段与 tracking 虚拟字段身份，生成规范权限 JSON。
- Modify: `backend/apps/datasource/crud/permission.py`：构建物理字段与 JSON 子路径权限范围，同时保留现有字段过滤接口。
- Modify: `backend/apps/datasource/crud/sql_permission.py`：执行 JSON 路径权限校验并产生结构化权限异常。
- Modify: `backend/apps/datasource/crud/permission_errors.py`：记录 JSON 路径与拒绝类型审计字段。
- Modify: `backend/apps/datasource/api/datasource.py`：普通用户字段列表隐藏被禁止的 JSON 虚拟字段。
- Modify: `backend/apps/chat/curd/chat.py`：表/字段/JSON 权限精确校验缓存，行级权限实时刷新数据。
- Create: `frontend/src/views/system/permission/permissionFieldEntries.ts`：保留字段接口返回的 JSON 身份元数据并合并已保存开关。
- Modify: `frontend/src/views/system/permission/index.vue`：调用字段条目辅助函数，展示保持不变。
- Create: `frontend/scripts/check-permission-json-subfields.mjs`：验证 JSON 字段元数据保存和编辑回显。
- Modify: `frontend/package.json`：增加前端权限字段检查命令。
- Test: `backend/tests/test_sql_json_paths.py`
- Test: `backend/tests/test_dashboard_ai_sql_generator.py`
- Test: `tests/test_datasource_permission_roles.py`
- Test: `backend/tests/test_chat_history_loading.py`
- Test: `tests/test_chat_permission_boundaries.py`

---

### Task 1: 抽取共享 JSON 路径解析器

**Files:**
- Create: `backend/common/sql_json_paths.py`
- Create: `backend/tests/test_sql_json_paths.py`
- Modify: `backend/apps/dashboard/crud/ai_sql_generator.py:431`
- Test: `backend/tests/test_dashboard_ai_sql_generator.py`

**Interfaces:**
- Produces: `normalize_json_path(value: Any, *, postgres: bool = False) -> str`
- Produces: `json_path_segments(value: Any) -> tuple[str, ...] | None`
- Produces: `json_paths_intersect(left: str, right: str) -> bool`
- Produces: `extract_json_accesses(expression: exp.Expression, *, dialect: str) -> JsonAccessExtraction`
- Produces: `extract_sql_json_field_pairs(sql: str, dialect: str) -> tuple[set[tuple[str, str]], list[str]]`
- Consumed by: `ai_sql_generator.py` 和 Task 3 的 `sql_permission.py`

- [ ] **Step 1: 编写路径规范化、父子关系和跨方言提取失败测试**

在 `backend/tests/test_sql_json_paths.py` 覆盖以下断言：

```python
from sqlglot import parse_one

from common.sql_json_paths import (
    extract_json_accesses,
    json_paths_intersect,
    normalize_json_path,
)


def test_json_path_parent_child_intersection_is_structural():
    assert normalize_json_path("money") == "$.money"
    assert json_paths_intersect("$.payment", "$.payment.money") is True
    assert json_paths_intersect("$.payment.money", "$.payment") is True
    assert json_paths_intersect("$.payment.money", "$.payment.channel") is False


def test_mysql_json_extract_returns_static_access():
    statement = parse_one(
        "SELECT JSON_UNQUOTE(JSON_EXTRACT(e.personal, '$.money')) FROM event e",
        read="mysql",
    )
    result = extract_json_accesses(statement, dialect="mysql")
    assert {(item.table_alias, item.source_field, item.json_path) for item in result.accesses} == {
        ("e", "personal", "$.money")
    }
    assert result.issues == ()


def test_dynamic_json_path_is_reported_as_unresolved():
    statement = parse_one("SELECT JSON_EXTRACT(e.personal, e.path) FROM event e", read="mysql")
    result = extract_json_accesses(statement, dialect="mysql")
    assert result.accesses == ()
    assert result.issues[0].reason == "dynamic_path"
```

同一测试文件增加 PostgreSQL `->>`、`#>>` 和 ClickHouse `JSON_VALUE` 用例，并验证嵌套 PostgreSQL 运算符会合并为一个完整路径。

- [ ] **Step 2: 运行新测试并确认失败**

Run: `cd backend; .\.venv\Scripts\python.exe -m pytest tests/test_sql_json_paths.py -q`

Expected: FAIL，提示 `common.sql_json_paths` 不存在。

- [ ] **Step 3: 实现共享数据结构和提取器**

在 `backend/common/sql_json_paths.py` 定义不可变结果类型：

```python
from dataclasses import dataclass


@dataclass(frozen=True)
class JsonPathAccess:
    table_alias: str
    source_field: str
    json_path: str
    consumed_column_ids: frozenset[int]


@dataclass(frozen=True)
class JsonPathIssue:
    table_alias: str
    source_field: str
    reason: str


@dataclass(frozen=True)
class JsonAccessExtraction:
    accesses: tuple[JsonPathAccess, ...]
    issues: tuple[JsonPathIssue, ...]
    consumed_column_ids: frozenset[int]
```

实现要求：

- 路径按 SQLGlot JSONPath 节点解析，不能使用原始 SQL 字符串前缀匹配；
- `json_path_segments` 对属性名和数组下标生成确定段，动态下标返回 `None`；
- PostgreSQL 连续操作符合并成一个路径；
- 外层 `JSON_UNQUOTE`、类型转换和数值转换不重复产生访问；
- 每个成功访问记录底层 `exp.Column` 的 `id()`，供 Task 3 区分“路径访问”和“直接容器读取”；
- 未知方言、动态路径、非列容器和无法解析路径生成 `JsonPathIssue`。

- [ ] **Step 4: 让 AI SQL 生成校验复用共享解析器**

将 `ai_sql_generator.py` 的 `_normalized_json_path`、`_json_expression_column_name`、`_json_expression_path` 和 `_sql_json_field_pairs` 替换为对共享函数的导入。保留 `_sql_json_field_pairs` 名称作为模块内薄包装仅当现有测试直接引用它，否则直接调用 `extract_sql_json_field_pairs`。

- [ ] **Step 5: 运行共享解析器和 AI SQL 回归测试**

Run: `cd backend; .\.venv\Scripts\python.exe -m pytest tests/test_sql_json_paths.py tests/test_dashboard_ai_sql_generator.py -q`

Expected: PASS。

- [ ] **Step 6: 提交 Task 1**

```powershell
git add backend/common/sql_json_paths.py backend/tests/test_sql_json_paths.py backend/apps/dashboard/crud/ai_sql_generator.py backend/tests/test_dashboard_ai_sql_generator.py
git commit -m "重构：统一 JSON SQL 路径解析"
```

---

### Task 2: 规范化权限保存并保留前端 JSON 身份

**Files:**
- Create: `backend/apps/datasource/crud/permission_fields.py`
- Modify: `backend/apps/datasource/api/permission.py:101`
- Modify: `frontend/src/views/system/permission/index.vue:347`
- Create: `frontend/src/views/system/permission/permissionFieldEntries.ts`
- Create: `frontend/scripts/check-permission-json-subfields.mjs`
- Modify: `frontend/package.json:12`
- Test: `tests/test_datasource_permission_roles.py`

**Interfaces:**
- Produces: `canonicalize_permission_entries(session, user, datasource, table, entries) -> list[dict[str, Any]]`
- Produces: `fieldOptionsToPermissionEntries(options, savedEntries) -> PermissionFieldEntry[]`
- Consumes: 当前工作空间、数据源、物理表和 `sys_tenant_tracking_field`
- Consumed by: `permission_api._validate_permission_rule_scope` 与 Task 3 权限范围构建

- [ ] **Step 1: 编写服务端字段身份规范化失败测试**

在 `tests/test_datasource_permission_roles.py` 的权限 API 测试夹具中创建：

- `core_field` 物理容器 `personal`；
- 当前工作空间的 tracking 字段 `personal.money`，`source_field=personal`，`json_path=$.money`；
- 另一工作空间或另一数据源的同名 tracking 字段。

增加以下测试：

```python
def test_permission_save_canonicalizes_json_subfield_from_workspace_metadata(session, workspace_admin):
    payload = _permission_rule_payload(
        field_entries=[{
            "field_id": "tracking:event:personal.money",
            "field_name": "personal.money",
            "source_field": "personal",
            "json_path": "$.money",
            "is_json_subfield": True,
            "enable": False,
        }]
    )
    saved = asyncio.run(permission_api.save_rule.__wrapped__(session, workspace_admin, payload))
    entry = saved["permissions"][0]["permissions"][0]
    assert entry["field_id"] == "tracking:event:personal.money"
    assert entry["source_field"] == "personal"
    assert entry["json_path"] == "$.money"
    assert entry["is_json_subfield"] is True


def test_permission_save_rejects_forged_json_path(session, workspace_admin):
    payload = _permission_rule_payload(field_entries=[{
        "field_id": "tracking:event:personal.money",
        "field_name": "personal.money",
        "source_field": "personal",
        "json_path": "$.channel",
        "is_json_subfield": True,
        "enable": False,
    }])
    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(permission_api.save_rule.__wrapped__(session, workspace_admin, payload))
    assert exc_info.value.status_code == 400
```

另加跨工作空间、跨数据源、错误物理容器和不存在 tracking ID 的拒绝测试，以及数字物理字段 ID 保持原格式的回归测试。

- [ ] **Step 2: 运行服务端保存测试并确认失败**

Run: `cd backend; .\.venv\Scripts\python.exe -m pytest ..\tests\test_datasource_permission_roles.py -k "permission_save and (json_subfield or physical_field)" -q`

Expected: FAIL，当前保存逻辑未校验或保留 JSON 路径身份。

- [ ] **Step 3: 实现服务端规范化模块**

`permission_fields.py` 必须：

- 数字 ID 只匹配目标 `table_id` 下的 `CoreField`；
- `tracking:{table_name}:{field_name}` 只匹配当前工作空间、数据源和表的 `TenantTrackingFieldModel`；
- 验证元数据的 `source_field` 存在于目标表物理字段中；
- 使用共享 `normalize_json_path` 生成规范路径；
- 前端提交的 `field_name/source_field/json_path/is_json_subfield` 与服务端规范值不一致时抛出 `ValueError`；
- 输出只包含允许持久化的规范键，保留 `enable` 和服务端字段注释；
- 无工作空间上下文的全局平台权限规则拒绝保存 tracking JSON 子字段，但继续允许物理字段权限。

在 `permission_api._validate_permission_rule_scope` 验证数据源和表后调用该函数，并把规范条目写回 `permission["permissions"]`；将 `ValueError` 转换为 HTTP 400，不调用 `save_rule_dto`。

- [ ] **Step 4: 编写前端字段条目辅助函数测试**

`frontend/scripts/check-permission-json-subfields.mjs` 使用 TypeScript `transpileModule` 加载 `permissionFieldEntries.ts`，断言：

```javascript
const options = [{
  id: 'tracking:event:personal.money',
  field_name: 'personal.money',
  field_comment: '付费金额',
  source_field: 'personal',
  json_path: '$.money',
  is_json_subfield: true,
}]
const result = fieldOptionsToPermissionEntries(options, [{
  field_id: 'tracking:event:personal.money',
  enable: false,
}])
assert.deepEqual(result, [{
  field_id: 'tracking:event:personal.money',
  field_name: 'personal.money',
  field_comment: '付费金额',
  source_field: 'personal',
  json_path: '$.money',
  is_json_subfield: true,
  enable: false,
}])
```

同时验证数字物理字段、未保存新字段默认开启、字符串 ID 精确匹配且不经过 JavaScript Number 转换。

- [ ] **Step 5: 运行前端测试并确认失败**

Run: `cd frontend; node scripts/check-permission-json-subfields.mjs`

Expected: FAIL，辅助模块不存在。

- [ ] **Step 6: 实现前端元数据保留，保持 UI 不变**

在 `permissionFieldEntries.ts` 定义 `PermissionFieldOption`、`PermissionFieldEntry` 和 `fieldOptionsToPermissionEntries`。修改 `handleTableIdChange` 与 `handleEditeTable`，删除当前只解构 `id/field_name/field_comment` 的映射，统一调用辅助函数。

不得修改模板、样式、字段显示名称或开关组件。`package.json` 增加：

```json
"test:permission-json-fields": "node scripts/check-permission-json-subfields.mjs"
```

- [ ] **Step 7: 运行 Task 2 测试**

Run: `cd backend; .\.venv\Scripts\python.exe -m pytest ..\tests\test_datasource_permission_roles.py -k "permission_save and (json_subfield or physical_field)" -q`

Run: `cd frontend; npm run test:permission-json-fields`

Run: `cd frontend; npx vue-tsc -b`

Expected: 全部 PASS。

- [ ] **Step 8: 提交 Task 2**

```powershell
git add backend/apps/datasource/crud/permission_fields.py backend/apps/datasource/api/permission.py tests/test_datasource_permission_roles.py frontend/src/views/system/permission/index.vue frontend/src/views/system/permission/permissionFieldEntries.ts frontend/scripts/check-permission-json-subfields.mjs frontend/package.json
git commit -m "功能：保存 JSON 子字段权限"
```

---

### Task 3: 在统一 SQL 权限入口执行 JSON 路径限制

**Files:**
- Modify: `backend/apps/datasource/crud/permission.py:851`
- Modify: `backend/apps/datasource/crud/sql_permission.py:63`
- Modify: `backend/apps/datasource/crud/permission_errors.py:36`
- Modify: `backend/apps/datasource/api/datasource.py:704`
- Test: `tests/test_datasource_permission_roles.py`
- Test: `backend/tests/test_sql_json_paths.py`

**Interfaces:**
- Produces: `ColumnPermissionScope(fields: list[CoreField], denied_json_paths: dict[str, set[str]])`
- Produces: `get_column_permission_scope(session: SessionDep, current_user: CurrentUser, table: CoreTable, fields: list[CoreField], contain_rules: list[Any]) -> ColumnPermissionScope`
- Produces: `SqlPermissionScopeError(message, *, fields=(), json_paths=(), rule_type=None)`
- Consumes: Task 1 `extract_json_accesses/json_paths_intersect`
- Consumes: Task 2 规范化权限条目

- [ ] **Step 1: 编写权限范围和 SQL 拒绝测试**

在 `tests/test_datasource_permission_roles.py` 增加 fixture：容器 `personal` 开启、`personal.money` 关闭、`personal.channel` 开启。覆盖：

```python
def test_json_subfield_permission_allows_sibling_path(session, restricted_user, datasource):
    validate_sql_scope(
        session,
        restricted_user,
        datasource,
        "SELECT JSON_EXTRACT(e.personal, '$.channel') FROM event e",
    )


@pytest.mark.parametrize("sql", [
    "SELECT JSON_EXTRACT(e.personal, '$.money') FROM event e",
    "SELECT JSON_EXTRACT(e.personal, '$.money.currency') FROM event e",
    "SELECT JSON_EXTRACT(e.personal, '$') FROM event e",
    "SELECT e.personal FROM event e",
    "SELECT e.* FROM event e",
    "SELECT * FROM event e",
    "SELECT JSON_EXTRACT(e.personal, e.path) FROM event e",
])
def test_json_subfield_permission_rejects_sensitive_access(session, restricted_user, datasource, sql):
    with pytest.raises(ValueError, match="无权限"):
        validate_sql_scope(session, restricted_user, datasource, sql)
```

增加 CTE、嵌套 SELECT、别名、PostgreSQL 和 ClickHouse 等价表达式测试，并断言普通用户错误响应不包含 `personal` 或 `$.money`。

- [ ] **Step 2: 运行 SQL 权限测试并确认失败**

Run: `cd backend; .\.venv\Scripts\python.exe -m pytest ..\tests\test_datasource_permission_roles.py -k "json_subfield_permission" -q`

Expected: FAIL，现有范围只包含物理字段。

- [ ] **Step 3: 扩展列权限范围**

在 `permission.py` 增加：

```python
@dataclass(frozen=True)
class ColumnPermissionScope:
    fields: list[CoreField]
    denied_json_paths: dict[str, set[str]]
```

`get_column_permission_scope` 遍历适用于当前用户的 column 权限：

- 数字物理字段条目继续过滤 `fields`；
- 禁用且规范结构完整的 JSON 条目加入 `denied_json_paths[source_field]`；
- JSON 权限不把整个 `source_field` 从物理字段集合删除；
- 配置结构无效时抛出明确配置异常，不能静默放开；
- 现有 `get_column_permission_fields` 委托该函数并只返回 `.fields`，保持调用方兼容。

`build_permission_scope` 保存 `denied_json_paths`，同时保留 `fields/denied_fields`。

- [ ] **Step 4: 扩展 SQL 校验**

`validate_sql_columns` 对每个 SELECT：

1. 用 Task 1 提取 JSON 访问并映射表别名到物理表；
2. 对每个访问与该容器的禁用路径调用 `json_paths_intersect`；
3. 有交集时抛出 `SqlPermissionScopeError`；
4. 任一 `JsonPathIssue` 涉及存在禁用子路径的容器时安全拒绝；
5. 记录已消费的底层 `Column` 节点 ID；
6. 普通列遍历跳过这些已消费节点，其他对受限 JSON 容器的直接使用按整个容器读取拒绝；
7. `SELECT *` 的限制集合同时考虑 `denied_fields` 和非空 `denied_json_paths`。

`SqlPermissionScopeError.__str__` 保持现有“无权限”分类标记，但调用方给普通用户的内容继续由 `safe_query_error_message` 脱敏。

- [ ] **Step 5: 隐藏普通用户字段列表中的禁用 JSON 子字段**

在 `_build_field_list_items` 完成物理字段和 tracking 字段合并后，根据 `get_column_permission_scope().denied_json_paths` 过滤精确被禁路径及其父子路径。管理员不应用该过滤。不要隐藏同一容器中的授权同级字段。

- [ ] **Step 6: 扩展结构化审计**

`audit_permission_denied` 增加可选参数：

```python
json_paths: list[str] | set[str] | tuple[str, ...] | None = None,
rule_type: str | None = None,
```

SQL 执行和 Smart Q&A 捕获 `SqlPermissionScopeError` 时，把异常上的 `fields/json_paths/rule_type` 传入审计。用户响应仍只包含统一权限提示。使用 `caplog` 验证服务端日志包含规范路径而返回体不包含路径。

- [ ] **Step 7: 运行 Task 3 测试和现有权限回归**

Run: `cd backend; .\.venv\Scripts\python.exe -m pytest ..\tests\test_datasource_permission_roles.py tests/test_sql_json_paths.py ..\tests\test_query_executor.py -q`

Expected: PASS。

- [ ] **Step 8: 提交 Task 3**

```powershell
git add backend/apps/datasource/crud/permission.py backend/apps/datasource/crud/sql_permission.py backend/apps/datasource/crud/permission_errors.py backend/apps/datasource/api/datasource.py backend/tests/test_sql_json_paths.py tests/test_datasource_permission_roles.py
git commit -m "功能：校验 JSON 子字段访问权限"
```

---

### Task 4: 修复 Smart Q&A 历史缓存误封

**Files:**
- Modify: `backend/apps/chat/curd/chat.py:494`
- Modify: `backend/tests/test_chat_history_loading.py:342`
- Modify: `tests/test_chat_permission_boundaries.py:291`

**Interfaces:**
- Consumes: `validate_sql_scope` 精确表、物理字段和 JSON 路径结果
- Consumes: `has_applicable_row_permissions(session: SessionDep, current_user: CurrentUser, ds: CoreDatasource, tables: list[str] | None = None, single_table: CoreTable | None = None) -> bool`
- Produces: 历史缓存判定：字段权限通过即复用，行级权限实时刷新

- [ ] **Step 1: 编写合法字段缓存和行权限刷新失败测试**

新增或改写测试，明确区分两类行为：

```python
def test_history_keeps_cached_data_when_sql_uses_only_allowed_fields():
    engine = _engine_with_chat_permission_tables()
    current_user = SimpleNamespace(id=2, isAdmin=False, tenant_id=1)
    cached = {"fields": ["order_id"], "data": [{"order_id": 99}]}
    with Session(engine) as session:
        _insert_permission_fixture(session)
        session.add(Chat(
            id=1,
            create_by=2,
            create_time=datetime.datetime(2026, 7, 13),
            datasource=1,
            engine_type="PostgreSQL",
            brief="allowed cache",
        ))
        session.add(ChatRecord(
            id=1,
            chat_id=1,
            create_by=2,
            datasource=1,
            sql="select order_id from orders",
            data=json.dumps(cached),
        ))
        session.commit()
        result = chat_crud.get_chat_with_records(session, 1, current_user, None, with_data=False)
    assert result.records[0]["data"]["data"] == [{"order_id": 99}]
    assert result.records[0]["error"] is None


def test_history_refreshes_data_when_row_permission_applies(monkeypatch):
    engine = _engine_with_chat_permission_tables()
    current_user = SimpleNamespace(id=2, isAdmin=False, tenant_id=1)
    monkeypatch.setattr(
        chat_crud,
        "_execute_dashboard_chart_sql",
        lambda *args, **kwargs: {
            "status": "success",
            "fields": ["channel"],
            "data": [{"channel": "allowed"}],
        },
    )
    with Session(engine) as session:
        _insert_row_permission_fixture(session)
        session.add(Chat(
            id=1,
            create_by=2,
            create_time=datetime.datetime(2026, 7, 13),
            datasource=1,
            engine_type="PostgreSQL",
            brief="row refresh",
        ))
        session.add(ChatRecord(
            id=1,
            chat_id=1,
            create_by=2,
            datasource=1,
            sql="select channel from orders",
            data=json.dumps({"fields": ["channel"], "data": [{"channel": "stale"}]}),
        ))
        session.commit()
        result = chat_crud.get_chat_with_records(session, 1, current_user, None, with_data=False)
    assert result.records[0]["data"]["data"] == [{"channel": "allowed"}]
```

保留并扩展“原 SQL 命中当前禁用字段或 JSON 路径时清除 SQL、图表和数据”的测试。

- [ ] **Step 2: 运行历史测试并确认失败**

Run: `cd backend; .\.venv\Scripts\python.exe -m pytest tests/test_chat_history_loading.py ..\tests\test_chat_permission_boundaries.py -k "history or cached_data" -q`

Expected: 至少合法字段缓存测试 FAIL，因为 `has_applicable_permissions` 仍把任意字段规则视为缓存失效。

- [ ] **Step 3: 将实时刷新判定收窄为行级权限**

在 `chat.py`：

- `_record_allowed_by_current_permissions` 继续调用 `validate_sql_scope`，因此物理字段和 JSON 路径变化会精确拒绝；
- `_record_requires_live_data_for_current_permissions` 改用 `has_applicable_row_permissions`，不再调用 `has_applicable_permissions`；
- 将 `record_cache_requires_scrub` 重命名为 `record_cache_requires_refresh`；
- `include_record_data=True` 且需要刷新时，通过 `get_chart_data_with_user` 获取当前行权限结果并只用于响应，不写回历史缓存；
- 实时刷新返回权限失败时使用统一权限数据块；
- `include_record_data=False` 的轻量历史列表不执行 SQL；
- 派生分析和预测缓存继续在源记录命中行级权限时清除，避免旧总结泄露超范围数据。

- [ ] **Step 4: 运行历史与导出权限回归测试**

Run: `cd backend; .\.venv\Scripts\python.exe -m pytest tests/test_chat_history_loading.py ..\tests\test_chat_permission_boundaries.py tests/test_analysis_assistant_permissions.py tests/test_dashboard_permission_cache.py -q`

Expected: PASS。

- [ ] **Step 5: 提交 Task 4**

```powershell
git add backend/apps/chat/curd/chat.py backend/tests/test_chat_history_loading.py tests/test_chat_permission_boundaries.py
git commit -m "修复：按实际字段权限加载聊天历史"
```

---

### Task 5: 集成验证与本地验收

**Files:**
- Modify only if verification exposes a scoped defect in Tasks 1-4.

**Interfaces:**
- Consumes: Tasks 1-4 的完整权限链路
- Produces: 可复现的自动化和本地 UI 验收证据

- [ ] **Step 1: 运行后端目标测试集合**

Run:

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest `
  tests/test_sql_json_paths.py `
  tests/test_dashboard_ai_sql_generator.py `
  tests/test_chat_history_loading.py `
  tests/test_analysis_assistant_permissions.py `
  tests/test_dashboard_permission_cache.py `
  ..\tests\test_datasource_permission_roles.py `
  ..\tests\test_chat_permission_boundaries.py `
  ..\tests\test_query_executor.py -q
```

Expected: PASS，无失败或错误。

- [ ] **Step 2: 运行前端权限测试与生产构建**

Run: `cd frontend; npm run test:permission-json-fields`

Run: `cd frontend; npm run build`

Expected: 两条命令均成功，权限页面模板和样式没有变化。

- [ ] **Step 3: 启动或重启本地三服务栈**

按仓库 `AGENTS.md` 的本地运行手册执行 `powershell -ExecutionPolicy Bypass -File .\tools\stack-local.ps1`，保持后端 `8000`、MCP `8001`、前端 `5173`，并使用权威 `SHUZHI_DB_*`、`SHUZHI_REDIS_*` 设置。确认：

- `http://127.0.0.1:5173/` 返回 200；
- `http://127.0.0.1:8000/api/v1/system/getLoginMethod` 返回 200 或 401；
- 三个端口均处于监听状态。

- [ ] **Step 4: 在浏览器完成权限规则回显验收**

使用测试工作空间管理员进入当前扁平字段权限页面：

1. 打开 `flam / event` 字段禁止规则；
2. 关闭 `personal.money` 并保存；
3. 重新打开同一规则；
4. 确认 `personal.money` 仍关闭，字段列表布局和文案未变化。

不得在代码或种子脚本中硬编码该测试规则。若使用现有共享环境规则，先记录原值，验收后恢复原值；不要在未确认的情况下永久修改其他用户权限。

- [ ] **Step 5: 验证实时与历史查询**

使用绑定该规则的测试普通用户验证：

- “近七日 ARPU”读取 `personal.money`，实时和刷新后的历史均显示统一权限提示；
- “各渠道来源的七日留存率分析”只读取 `adinfo/uid/dt/prod/event`，实时和刷新后的历史均正常展示；
- 服务端审计日志包含拒绝路径，浏览器响应和页面不显示具体路径。

- [ ] **Step 6: 检查最终差异和工作区边界**

Run: `git diff --check`

Run: `git status --short`

Expected: 只包含本计划涉及的代码和测试；不包含 `.codex-runtime`、日志、备份、测试数据库数据或其他用户的未跟踪文件。

- [ ] **Step 7: 提交验证中产生的必要修正**

仅当 Step 1-6 暴露本计划范围内问题且产生代码修正时执行：

```powershell
git add backend/common/sql_json_paths.py backend/apps/dashboard/crud/ai_sql_generator.py backend/apps/datasource/crud/permission_fields.py backend/apps/datasource/api/permission.py backend/apps/datasource/crud/permission.py backend/apps/datasource/crud/sql_permission.py backend/apps/datasource/crud/permission_errors.py backend/apps/datasource/api/datasource.py backend/apps/chat/curd/chat.py backend/tests/test_sql_json_paths.py backend/tests/test_dashboard_ai_sql_generator.py backend/tests/test_chat_history_loading.py tests/test_datasource_permission_roles.py tests/test_chat_permission_boundaries.py frontend/src/views/system/permission/index.vue frontend/src/views/system/permission/permissionFieldEntries.ts frontend/scripts/check-permission-json-subfields.mjs frontend/package.json
git diff --cached --check
git commit -m "测试：完善 JSON 子字段权限回归"
```

若没有代码修正，不创建空提交。

---

## 完成定义

- `personal.money` 能在当前扁平字段列表中单独关闭并正确回显；
- 保存的 JSON 权限身份由服务端工作空间元数据规范化，伪造路径无法写入；
- 物理字段、JSON 精确路径、父子路径、直接容器、星号和动态路径均按设计执行；
- 同级授权路径和同表其他授权字段不被误封；
- Smart Q&A 实时、历史、导出、看板和分析助手通过统一 SQL 权限入口得到一致结果；
- 只有行级权限触发历史数据实时刷新；
- 普通用户响应不泄露敏感路径，服务端审计可定位；
- 后端目标测试、前端权限测试和生产构建全部通过。
