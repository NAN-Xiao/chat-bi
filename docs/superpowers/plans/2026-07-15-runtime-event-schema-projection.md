# 请求级事件属性 Schema 投影实现计划

**目标：** 修复业务 SQL 上下文先生成 Schema、后选择 Data Skill 导致事件属性无法进入 `m-schema` 的链路矛盾，并支持一个问题动态投影多个事件下的相关 JSON 属性。

**架构：** `BusinessSqlContextService` 先选择 Data Skills，再把 `question + data_skill_text` 传给 Schema 构建器。Schema 构建器从当前工作空间事件字典中只选择本次请求明确涉及的事件属性，验证事件表、事件名字段和 JSON 宿主字段均属于当前权限可见 Schema，随后按数据源方言编译为请求级表达式并追加到 `m-schema`；不写入 `sys_tenant_tracking_field`。

**约束：**

- 支持一个问题命中多个事件，并按事件分别输出属性块和必需事件谓词。
- 只投影问题或 Data Skill 明确提到的属性，不展开命中事件的全部属性。
- 同名属性保留事件边界；不跨事件静默合并冲突类型或 JSONPath。
- 宿主字段、事件名字段或事件表无效时不输出表达式，并生成明确 warning。
- 数组/对象容器属性暂不自动展开。
- 复用现有 `compile_tracking_json_expression()`，不新增业务域硬编码和兼容回退。
- 普通数据源、无事件字典工作空间和未命中事件属性的问题保持原行为。

## 任务

- [x] 新增 `backend/tests/test_tracking_event_schema_projection.py`，先验证 Data Skill 单事件命中、多事件命中、无关属性排除、宿主字段缺失、容器字段排除及 MySQL/PostgreSQL/ClickHouse 表达式。
- [x] 新增 `backend/apps/system/crud/tracking_event_schema.py`，提供请求级事件属性选择、验证、编译和格式化接口。
- [x] 调整 `backend/apps/datasource/crud/datasource.py`，让工作空间字典 Schema 接收 `data_skill_text` 并追加事件属性块和 warnings。
- [x] 调整 `backend/apps/datasource/crud/sql_engine.py`，将调用顺序改为 `Data Skills -> Schema -> Tracking Rules`，并把 Data Skill 传入 Schema。
- [x] 更新 `backend/tests/test_sql_engine_context.py`，验证调用顺序和参数透传。
- [x] 运行聚焦测试、相关后端回归测试与 Ruff 静态检查。

## 验收

对于“使用折线图展示近七天 ARPPU 趋势”，当 Data Skill 明确要求 `PayBuyRet`、`personal.ed_money`、`personal.ed_isSuccess` 时，本次 `m-schema` 必须包含两个编译后的 JSON 表达式和 `event = 'PayBuyRet'` 的事件边界说明，不得把它们当作物理列，也不得重新允许 `paytotal` 回退。
