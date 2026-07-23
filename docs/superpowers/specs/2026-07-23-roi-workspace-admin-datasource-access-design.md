# ROI 工作空间管理员数据源权限设计

## 背景

ROI 看板属于工作空间共享能力，入口仅对当前工作空间的 `owner` 和 `admin` 开放。
当前后端虽然已校验工作空间角色，但仍要求每个管理员额外获得 ROI 配置数据源的
`core_datasource_user` 账号级授权。

以 flam 空间为例：

- 工作空间绑定数据源为 `flam`；
- ROI 配置数据源为独立的 `ROI_flam`；
- 工作空间管理员如果没有 `ROI_flam` 的账号级授权，接口会返回
  `can_execute=false`、`can_edit=false`；
- 前端因此禁用添加和编辑按钮，无法打开 ROI SQL 编辑抽屉。

这使工作空间管理员角色与 ROI 管理能力不一致，并产生不必要的逐账号授权成本。

## 目标

当前工作空间的 `owner` 和 `admin` 自动获得该空间已配置 ROI 数据源的完整 ROI 权限：

- 查看 ROI 看板和图表；
- 执行 ROI 图表 SQL；
- 新建、编辑、排序和删除 ROI 图表；
- 打开 ROI SQL 编辑抽屉。

该权限只在 ROI 功能链路内生效，不扩展到 Smart Q&A、普通看板、数据源管理或其他功能。

## 非目标

- 不修改工作空间与物理数据源的单绑定模型；
- 不自动写入或删除 `core_datasource_user`；
- 不允许普通 `member` 访问 ROI 看板；
- 不允许 SaaS 全局管理员绕过真实工作空间上下文；
- 不改变普通数据源权限、行级权限或 SQL 安全策略。

## 权限模型

ROI 数据源候选集合调整为：

```text
工作空间绑定数据源
∪ 账号直接授权数据源
∪ 当前工作空间有效 ROI 配置的数据源
```

候选集合计算前仍必须通过 `require_roi_workspace_admin()`：

- 存在真实工作空间上下文；
- 当前角色为 `owner` 或 `admin`；
- 当前上下文不是 SaaS 全局管理员。

候选数据源最终仍需满足：

- `core_datasource.status` 大小写不敏感地等于 `success`；
- ROI 配置记录属于当前工作空间；
- ROI 配置记录 `deleted=false`。

因此，其他空间的管理员、当前空间的普通成员、失效配置和不可用数据源均不会获得权限。

## 实现范围

### 后端

在 `backend/apps/roi_dashboard/permissions.py` 中：

1. 查询当前管理工作空间的有效 `core_roi_workspace_config.datasource_id`；
2. 将其加入 `list_roi_accessible_datasource_ids()` 的候选集合；
3. 继续使用现有数据源状态过滤；
4. `has_roi_datasource_access()`、配置响应、图表读取、SQL 执行和写操作继续复用同一权限函数。

这样可以保持权限判定单一来源，避免各 ROI API 分别实现角色例外。

### 前端

无需修改。

现有前端已经根据后端的 `config.can_execute`、`config.can_edit` 和图表级
`can_execute`、`can_edit` 控制按钮和抽屉。后端返回 `true` 后，现有交互自动启用。

### 数据库

无需迁移和数据修复。

权限由当前空间角色和 ROI 配置动态计算。管理员降级、退出空间或更换 ROI 数据源后，
访问结果随当前数据即时变化，不会留下账号级授权记录。

## 数据流

```text
用户进入 ROI 看板
→ 校验当前空间角色为 owner/admin
→ 读取空间绑定数据源、账号直接授权、当前空间 ROI 配置数据源
→ 过滤 status != success 的数据源
→ ROI 配置数据源在可访问集合中
→ config.can_execute/config.can_edit = true
→ 前端启用图表执行、添加和编辑
→ ROI SQL 编辑抽屉可打开
```

## 错误处理

- 无工作空间或非 `owner/admin`：保持 `403`；
- 当前空间未配置 ROI 数据源：保持现有未配置提示；
- ROI 数据源不存在或状态非 `success`：保持无数据源权限状态；
- ROI SQL 不安全或执行失败：继续由现有查询执行器处理，不因角色隐式授权而放宽。

## 测试

在 `backend/tests/test_roi_dashboard_permissions.py` 增加或调整用例：

1. 工作空间管理员无需账号直接授权，也能访问当前空间有效 ROI 配置数据源；
2. 工作空间绑定和账号直接授权仍然有效；
3. 普通成员仍被拒绝；
4. 其他工作空间的 ROI 配置数据源不会泄漏；
5. 已删除 ROI 配置不会授权；
6. 状态非 `success` 的数据源不会授权。

运行 ROI 权限、服务、API 和查询执行相关测试，确认配置返回、图表读取及 SQL 执行行为一致。

## 验收标准

- `pengtong@elex-tech.com` 切换到 flam 空间后，ROI 配置接口返回
  `can_execute=true`、`can_edit=true`；
- ROI 图表接口返回图表级 `can_execute=true`、`can_edit=true`；
- 添加和编辑按钮可用，ROI SQL 编辑抽屉可以打开；
- 账号无需新增 `core_datasource_user` 记录；
- 该账号在非 flam 空间及普通数据源功能中的权限不变。
