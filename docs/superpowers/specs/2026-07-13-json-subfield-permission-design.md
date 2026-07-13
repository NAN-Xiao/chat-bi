# JSON 子字段级权限设计

## 背景

当前字段权限只对物理列生效。对于 `event.personal` 这类 JSON 容器，权限系统能够禁止整个 `personal`，但不能只禁止 `personal.money`。因此，使用 `JSON_EXTRACT(personal, '$.money')` 等表达式的查询仍会通过物理列校验。

同时，Smart Q&A 历史回放把“用户在查询表上命中任意表、字段或行权限规则”直接视为旧缓存不可信。即使历史 SQL 只使用已授权字段，也会被替换成“没有查看权限”。例如，禁止 `event.pay` 后，只使用 `event.adinfo` 的渠道留存查询仍被误拦截。

本设计增加通用、数据源无关的 JSON 子字段级权限，并修正历史缓存判定粒度。JSON 字段定义继续来自工作空间元数据，不在平台运行时代码中硬编码业务字段或路径。

## 目标

- 管理员可在现有扁平字段权限列表中单独禁止 JSON 子字段，例如 `personal.money`。
- SQL 执行、历史回放、导出和其他复用统一 SQL 权限入口的场景使用相同的 JSON 路径权限判定。
- 禁止 JSON 子路径后，不能通过读取父路径、整个 JSON 容器、`SELECT *` 或动态路径绕过权限。
- 查询只使用同一物理表中的其他授权字段时继续正常执行和展示历史缓存。
- 保持现有物理字段权限、表权限、行权限和普通权限规则数据兼容。
- 权限页面保持当前扁平列表、开关含义、展示内容和交互布局不变。

## 非目标

- 不新增专用 JSON 权限表。
- 不把 JSON 子字段写入 `core_field`。
- 不迁移或猜测现有权限记录中的 JSON 子字段含义。
- 不修改工作空间数据字典的 JSON 字段维护流程。
- 不在共享代码中增加 `personal.money`、ARPU、游戏或其他领域硬编码。

## 现有能力

`sys_tenant_tracking_field` 已使用以下字段描述 JSON 子字段：

- `table_name`
- `field_name`，例如 `personal.money`
- `source_field`，例如 `personal`
- `json_path`，例如 `$.money`
- `semantic_type`
- `field_role`

数据源字段列表接口已把这些记录合并为虚拟字段项，并使用稳定字符串 ID，例如：

```text
tracking:event:personal.money
```

该 ID 仅用于前后端定位工作空间元数据，不是物理字段 ID、SQL 表达式或用户可见文案。

## 方案选择

采用扩展现有 `ds_permission.permissions` JSON 结构的方案，不增加数据库表。

没有选择独立 JSON 权限表，是因为现有权限规则、用户绑定和字段列表已能承载该能力，新增表会引入不必要的迁移和规则关联复杂度。没有选择把 JSON 子字段写入 `core_field`，是因为工作空间元数据不能污染物理数据源字段模型。

## 权限数据结构

普通物理字段保持现有结构：

```json
{
  "field_id": 878,
  "field_name": "pay",
  "field_comment": "",
  "enable": false
}
```

JSON 子字段保存完整的规范定位信息：

```json
{
  "field_id": "tracking:event:personal.money",
  "field_name": "personal.money",
  "field_comment": "",
  "source_field": "personal",
  "json_path": "$.money",
  "is_json_subfield": true,
  "enable": false
}
```

前端继续使用现有扁平列表。构造和编辑 `columnForm.permissions` 时保留字段接口返回的 `source_field`、`json_path` 和 `is_json_subfield`，不改变列表显示内容。

## 服务端规范化

权限保存接口不能信任前端提交的 JSON 路径。对于 `is_json_subfield=true` 或字符串 `field_id` 以 `tracking:` 开头的条目，服务端必须使用当前权限管理上下文中的以下边界重新查询 `sys_tenant_tracking_field`：

- 当前工作空间
- 当前数据源
- 当前物理表
- 虚拟字段 ID 对应的 `field_name`

服务端从元数据记录生成并保存规范的 `field_name`、`source_field`、`json_path` 和 `is_json_subfield`。以下情况拒绝保存并返回明确的配置错误：

- 虚拟字段不存在；
- 虚拟字段属于其他工作空间、数据源或表；
- `source_field` 不是目标表的可用物理字段；
- JSON 路径为空或无法规范化；
- 前端提交的稳定 ID 与元数据字段不一致。

普通物理字段条目继续按数字 `core_field.id` 校验。服务端同样应以数据库记录为准规范化物理字段名称，避免伪造字段 ID 与名称组合。

## 权限范围模型

`build_permission_scope` 在现有表字段集合之外，为每张物理表增加 JSON 权限信息：

```python
{
    "fields": {"uid", "personal", "adinfo"},
    "denied_fields": {"pay"},
    "denied_json_paths": {
        "personal": {"$.money"}
    },
}
```

禁止整个物理容器字段时，继续由 `denied_fields` 处理。允许物理容器但禁止部分子路径时，由 `denied_json_paths` 处理。

工作空间元数据是 JSON 路径身份的权威来源。权限配置只引用当前数据源和工作空间中的元数据，不跨数据源或工作空间推断同名路径。

## SQL JSON 访问提取

在 `sql_permission.py` 中增加独立的 JSON 访问提取器，输入 SQLGlot AST 和当前 SELECT 的物理表别名映射，输出规范访问集合：

```python
JsonPathAccess(
    table="event",
    source_field="personal",
    json_path="$.money",
)
```

提取器覆盖平台当前支持方言中的等价表达式：

- MySQL/StarRocks：`JSON_EXTRACT`、外层 `JSON_UNQUOTE`；
- PostgreSQL：`->`、`->>`、`#>`、`#>>`；
- ClickHouse：平台当前生成和接受的 JSON 提取函数；
- 通用：`JSON_VALUE`。

路径统一规范为 `$` 开头的点路径。数组下标保留为确定路径段。字符串常量路径可以校验；变量、列值、拼接结果或 SQLGlot 无法确定的动态路径视为不可安全验证。

现有 `ai_sql_generator.py` 中已有 JSON 表达式和路径解析能力。实施时应提取可复用的通用辅助逻辑，避免 SQL 生成校验和权限校验维护两套不一致的方言规则。

## 判定规则

对于每个 SQL JSON 访问和禁用路径，采用结构化路径段比较，不使用字符串前缀猜测。

- 访问路径等于禁用路径：拒绝；
- 访问路径是禁用路径的后代：拒绝；
- 访问路径是禁用路径的祖先：拒绝，因为父对象包含被禁用数据；
- 访问同级无交集路径：允许；
- 直接读取包含禁用子路径的物理 JSON 容器：拒绝；
- `SELECT *` 或 `table.*` 会返回包含禁用子路径的容器：拒绝；
- 动态路径、无法解析路径或无法可靠归属到物理表：安全失败并拒绝；
- 物理容器字段本身被禁用：无论访问哪个子路径都拒绝。

例如禁止 `personal.money` 后：

| SQL 访问 | 结果 |
| --- | --- |
| `JSON_EXTRACT(personal, '$.money')` | 拒绝 |
| `JSON_EXTRACT(personal, '$.money.currency')` | 拒绝 |
| `JSON_EXTRACT(personal, '$')` | 拒绝 |
| 直接选择 `personal` | 拒绝 |
| `JSON_EXTRACT(personal, '$.channel')` | 允许 |
| 选择 `adinfo` | 允许 |

## 容器列识别

SQLGlot 会同时把 JSON 表达式中的底层物理列识别为普通 `Column`。权限校验必须区分两种情况：

- 物理列只作为已成功解析的 JSON 路径表达式输入时，按具体 JSON 路径判定；
- 物理列在其他表达式或结果列中被直接使用时，视为读取整个容器。

不得因为 `personal` 物理列仍处于允许状态而跳过子路径校验，也不得把合法的 `personal.channel` 误判为直接读取整个容器。

## 历史缓存策略

历史记录继续先调用统一的 `validate_sql_scope` 使用当前权限重新校验原 SQL。

- SQL 命中被禁物理表、物理字段或 JSON 路径：清除 SQL、图表和数据缓存，返回统一权限失败；
- SQL 只使用授权字段和授权 JSON 路径：允许返回已保存缓存；
- 查询涉及当前用户生效的行级权限：不复用旧数据，使用当前行过滤重新执行只读 SQL；
- 数据源访问权已撤销或重新执行失败为权限错误：返回统一权限失败。

`_record_requires_live_data_for_current_permissions` 只应把会影响结果行集合的行级权限视为必须实时执行的原因。表、物理字段和 JSON 路径权限已由 `validate_sql_scope` 精确判定，不能仅因为表上存在任意权限规则就隐藏缓存。

## 错误与审计

普通用户统一收到：

```text
没有查看权限
```

不得向普通用户暴露被禁表、物理字段、JSON 容器、JSON 路径或规则名称。

服务端审计日志记录：

- 用户 ID；
- 工作空间 ID；
- 数据源 ID；
- 物理表；
- JSON 容器字段；
- 被拒绝的规范 JSON 路径；
- 操作入口；
- 拒绝原因类型，例如精确路径、父路径、子路径、直接容器、星号或动态路径。

## 配置失效处理

权限规则中的 JSON 子字段在工作空间元数据中被删除或修改后，不自动替换为相似字段，也不根据 `field_name` 猜测其他路径。

- 编辑规则时标记该条目无效并要求管理员重新选择；
- 权限执行时，如果已保存的规范路径结构完整，继续按保存路径执行限制，避免元数据删除导致权限静默放开；
- 如果历史条目缺少形成安全限制所需的结构，则配置校验失败，不把它自动解释为其他字段。

## 兼容性

- 现有数字 `field_id` 物理字段权限保持原行为；
- 现有表权限和行权限保持原行为；
- 不迁移现有权限 JSON；
- 不从旧权限的 `field_name` 推断 JSON 路径；
- 新 JSON 子字段权限在管理员保存规则后生效；
- 不增加数据库 schema 迁移。

## 测试策略

### 权限保存

- 保存合法工作空间 JSON 子字段时写入规范路径信息；
- 伪造其他工作空间、数据源、表或字段 ID 时拒绝；
- `source_field/json_path` 与服务端元数据不一致时拒绝保存；
- 编辑后 JSON 子字段开关状态正确回显；
- 现有物理字段权限保存和回显不回归。

### SQL 校验

- 禁止 `personal.money` 后拒绝精确路径；
- 拒绝其父路径、子路径、整个 `personal` 和 `SELECT *`；
- 允许 `personal.channel` 和其他物理字段；
- 动态路径和无法归属的 JSON 表达式安全失败；
- CTE、表别名、嵌套 SELECT 和输出别名不能绕过校验；
- MySQL、PostgreSQL、ClickHouse 的等价表达式产生一致判定；
- 已禁物理容器字段时所有子路径均拒绝。

### 业务入口

- Smart Q&A 实时 ARPU 查询读取禁用路径时拒绝；
- Smart Q&A 渠道留存只读取授权字段时通过；
- 渠道留存历史缓存正常展示，不再被同表其他字段规则误封；
- ARPU 历史 SQL 命中禁用路径时缓存被清理；
- 导出、看板 SQL、分析助手等复用统一 SQL 权限入口的场景保持同样结果；
- 行级权限历史数据按当前过滤重新执行；
- 数据源访问权撤销后历史数据仍不可见。

## 验收标准

- 在当前扁平权限列表中关闭 `personal.money` 并保存后，重新编辑能看到该开关保持关闭；
- `dongjinchao_t1` 查询近七日 ARPU 时实时和历史结果都显示统一权限提示；
- `dongjinchao_t1` 查询各渠道七日留存时实时和历史结果都正常展示；
- 直接读取 `personal`、读取 `personal.money` 父子路径、使用 `SELECT *` 或动态路径均不能绕过限制；
- 现有 `pay`、`allianceinfo` 物理字段权限继续生效；
- 普通用户响应不暴露敏感字段和路径，服务端审计保留定位信息。
