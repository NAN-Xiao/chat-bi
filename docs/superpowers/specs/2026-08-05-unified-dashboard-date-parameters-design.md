# 看板日期参数统一规则设计

## 背景

当前看板日期参数只接受两种组合：开始和结束参数同时出现，或者仅使用结束参数。仅使用开始参数会被判定为 `incomplete_parameters`。此外，日期过滤服务会识别物理表名 `event_realtime`，普通看板拒绝其显式日期范围，聊天执行路径则通过 `allow_realtime_current_day` 仅放行当天完整区间。

这些规则使同一套日期参数在不同 SQL 形态和不同物理表上产生不一致行为。目标是建立与业务表名无关的统一日期参数契约。

## 目标

1. 所有日期参数类型统一接受三种组合：仅开始参数、仅结束参数、开始和结束参数同时出现。
2. 普通看板、SQL 预览和聊天执行使用同一套参数校验与渲染规则。
3. 删除针对 `event_realtime` 的日期范围限制，不根据物理表名改变日期参数能力。
4. 保留现有参数类型、日期表达式、SQL 权限、数据源权限和只读 SQL 校验边界。

## 非目标

- 不改变日期表达式对“今日”“过去 7 天”等范围的解析语义。
- 不自动替换物理表，也不在 `event_realtime` 无历史数据时回退到其他表。
- 不保证任意数据源或物理表实际保存了所选日期范围的数据。
- 不放宽混合日期参数家族、无效参数类型或缺失日期配置等错误。

## 统一契约

每种日期参数类型都定义一个开始 token 和一个结束 token。SQL 正文中出现的受控 token 集合必须是以下三种之一：

- `{start}`
- `{end}`
- `{start, end}`

空集合仍表示 SQL 未使用看板日期参数。不同参数家族混用仍返回 `mixed_parameter_families` 或 `parameter_type_mismatch`。

SQL 运算符决定参数的业务含义。例如 `dt >= {{dashboard_start_yyyymmdd}}`、`dt = {{dashboard_start_yyyymmdd}}` 和 `dt <= {{dashboard_end_yyyymmdd}}` 都是合法模板；平台只负责校验 token、解析日期表达式并替换实际值，不推断或改写比较运算符。

## 实现边界

### 前端配置校验

`dashboardChartConfig.ts` 的 token 匹配逻辑改为接受上述三个集合。`DashboardSqlEditor` 继续复用该配置构建函数，因此生成、预览和应用入口自动获得一致行为，不增加页面特例。

### 后端日期准备

`validate_dashboard_date_parameter_sql` 使用同样的三个允许集合。`prepare_dashboard_date_filter` 根据 SQL 中实际存在的 token 进行替换；单 token SQL 只替换对应值，双 token SQL 替换起止值。

删除 `event_realtime` 表名判断、`allow_realtime_current_day` 参数及仅当天完整区间的分支。物理表解析仍用于权限和 SQL 安全处理，但不参与日期范围能力决策。

### 看板与聊天执行

删除普通看板预览和批量加载中“实时图表不支持自定义日期范围”的拦截。聊天执行不再传递实时表放行开关，直接使用共享日期准备逻辑。

统一处理后，只要日期配置有效，能力状态为 `available`，渲染后的 SQL 进入现有权限检查、缓存和执行流程。数据源返回空结果或数据库错误时，沿用现有显式结果，不做兼容兜底。

## 错误处理

- 无受控 token：保持现有 `missing_parameters` 或无日期过滤配置行为。
- 参数类型不存在：`invalid_parameter_type`。
- 不同 token 家族混用：`mixed_parameter_families`。
- token 家族与配置类型不一致：`parameter_type_mismatch`。
- 日期表达式或自定义范围无效：保持现有 `invalid_date_expression` / `invalid_date_range`。
- 查询范围没有业务数据：由数据源正常返回空结果，不转换为日期配置错误。

`incomplete_parameters` 不再用于合法的仅开始或仅结束模板；该错误标识可保留给其他调用方的错误分类兼容，但共享日期校验不再为这三种合法组合返回它。

## 测试设计

### 前端

- 现有双 token 和仅结束 token 配置继续通过。
- 新增仅开始 token 配置通过。
- 缺少配置、禁用配置、参数家族不匹配继续失败。

### 后端

- 参数化验证仅开始、仅结束和双 token 三种组合。
- 验证三种组合分别渲染正确日期值。
- 使用 `event_realtime` 的今日、历史范围和单 token SQL 与普通表得到相同日期能力和渲染结果。
- 更新聊天测试：历史范围和单 token 实时 SQL 从显式拒绝改为成功渲染。
- 覆盖普通看板预览路径，确认不再返回 `dashboard_date_filter_realtime`。

### 回归

- 运行前端日期配置测试。
- 运行后端看板日期过滤、看板预览和聊天日期过滤测试。
- 运行前端构建，确认 TypeScript 和 Vue 集成无回归。

## 风险与控制

移除实时表日期限制后，用户可以对 `event_realtime` 请求更长日期范围。平台不再根据表名替用户决定范围，查询性能和数据可用性由数据源、SQL 权限、查询超时及现有并发控制负责。该行为符合通用 BI 平台原则，避免在共享运行时硬编码业务表名。
