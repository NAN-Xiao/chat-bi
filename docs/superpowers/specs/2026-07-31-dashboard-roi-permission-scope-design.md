# 普通看板 ROI 数据源权限范围修复设计

## 背景

普通看板允许图表选择当前工作空间配置的 ROI 数据源。该数据源不要求用户单独获得通用数据源授权，因此看板执行器使用 datasource_access_checked=True 跳过重复的数据源可见性检查。当前实现同时用这个标志关闭 apply_user_permission_scope，导致针对当前用户配置的表禁止和字段禁止也被跳过。

## 目标

普通看板使用工作空间 ROI 数据源时，可以跳过重复的数据源访问检查，但仍必须执行当前用户的表禁止、字段禁止和既有行权限策略。禁止规则生效后，不得执行对应 SQL，也不得返回已有缓存或快照数据。

## 方案

保留 datasource_access_checked 的单一含义：上游已确认该数据源属于当前工作空间允许的执行数据源。validate_user_query_sql_or_raise 和 execute_user_query_or_raise 仍根据该标志跳过 has_datasource_access，但调用 prepare_query_sql 时始终启用 apply_user_permission_scope=True。

行权限继续使用普通看板现有的 deny_on_overlap 策略，不改变 SQL 重写、安全检查、数据源候选集或 ROI 专用看板执行器。

## 测试

1. 修改执行器契约测试，证明 datasource_access_checked=True 时仍把 apply_user_permission_scope=True 传给 SQL 权限准备流程。
2. 覆盖预校验和实际执行两个入口，避免审计通过但执行绕过，或审计拒绝后另一条路径仍执行。
3. 运行普通看板执行数据源、看板权限缓存、SQL 引擎上下文和 ROI 查询专项回归。

## 非目标

- 不改变 ROI 数据源的工作空间授权模型。
- 不要求普通成员额外获得 ROI 数据源的通用用户授权。
- 不改变管理员在普通数据源路径中的既有放行行为。
- 不修改规则数据、看板数据或 Redis 键格式。
