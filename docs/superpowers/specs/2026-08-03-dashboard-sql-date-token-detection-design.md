# 看板 SQL 日期参数识别修复设计

## 背景

已迁移的看板图表可以在顶层 `dateFilter` 中保存日期参数类型和日期表达式，但部分旧图表的 SQL Builder 配置没有 `timeField`。当前 SQL 编辑器仅根据 `timeField` 判断图表是否使用看板日期参数，因此会隐藏日期配置，并在同步 SQL Builder 日期状态时清空已经恢复的日期参数类型。

典型异常状态如下：

- SQL 包含合法的看板开始、结束日期 token。
- `dateFilter.parameterType` 已保存为合法值。
- `sourceConfig.sql.builder.timeField` 为空。
- 用户执行 SQL 时收到“SQL 包含看板日期参数，请明确选择日期参数类型”。

## 目标

- SQL 包含合法看板日期 token 时，即使 SQL Builder 没有 `timeField`，也启用并保留日期参数配置。
- 已保存的 `dateFilter.parameterType` 仍是编辑现有图表时的权威值。
- 新写的 SQL 包含日期 token 但尚未配置类型时，显示日期配置控件并要求用户明确选择。
- 不根据 SQL 字段名、图表字段或数据源自动猜测日期参数类型。
- 不改变无日期 token SQL 的现有行为。

## 方案比较

### 方案 A：同时识别 Builder 时间字段与 SQL token

将日期参数使用条件定义为：图表类型允许日期表达式，并且 SQL Builder 配置了 `timeField`，或者当前 SQL 含有合法看板日期 token。

优点：兼容 SQL Builder 和手工 SQL；无需补写业务字段；能修复已有迁移数据。缺点：日期能力判断需要扫描当前 SQL，但 SQL 长度有限且已有通用 token 扫描函数，成本可忽略。

### 方案 B：仅根据顶层 `dateFilter` 判断

优点：编辑已保存图表时直接。缺点：用户新写含 token 的 SQL 时，在首次保存前无法显示配置入口。

### 方案 C：迁移并补齐 Builder `timeField`

优点：保持旧判断不变。缺点：需要从 SQL 或结果字段猜测业务时间字段，容易产生错误语义，也会把手工 SQL 强行转换成 Builder 配置。

采用方案 A。

## 详细设计

### 日期参数使用条件

在 `DashboardSqlEditor.vue` 中复用现有 `scanDashboardDateParameterTokens(form.sql)`。日期参数能力在以下任一条件成立时启用：

1. SQL Builder 已配置非空 `timeField`。
2. 当前 SQL 扫描到至少一个受支持的看板日期 token。

图表类型的既有限制继续生效。指标卡仍遵循其显式日期表达式开关，不因 SQL token 扫描绕过该开关。

### 初始化与状态同步

打开编辑器时，继续先通过 `normalizeDashboardChartConfig(viewInfo)` 恢复顶层 `dateFilter`，再把 `dateFilter.parameterType` 写入表单。

当 SQL 含日期 token、Builder `timeField` 为空时，日期表达式控件保持启用，`syncDashboardDateParameterUsage()` 不再清空已恢复的 `pivotDateParameterType`。

当 SQL 不含日期 token 且 Builder 没有 `timeField` 时，沿用当前禁用和清理行为。

### 校验与错误处理

- SQL 含日期 token 且参数类型为空：显示现有必选提示并阻止预览或保存。
- SQL token 与所选类型不匹配：显示现有无效类型提示。
- 已保存的日期配置不合法：沿用迁移错误处理，不静默回退。
- 不设置默认参数类型，不从首列、透视字段或相似字段推断。

## 测试

补充针对以下行为的回归测试：

1. 表格 SQL 含日期 token、Builder `timeField` 为空、顶层类型已配置时，日期能力启用且类型不被清空。
2. 手工 SQL 新增日期 token、类型为空时，日期配置入口可用且预览被明确校验阻止。
3. SQL 不含日期 token且 Builder `timeField` 为空时，保持现有禁用行为。
4. Builder 有 `timeField` 时，保持现有日期表达式行为。
5. 指标卡仍受显式开关控制，不被 token 扫描自动启用。

## 范围

本次仅修改 SQL 编辑器的通用日期参数识别与对应测试，不修改数据库数据、后端日期契约、看板业务 SQL 或数据源特定规则。
