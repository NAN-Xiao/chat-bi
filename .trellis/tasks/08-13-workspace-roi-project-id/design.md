# 工作空间绑定 ROI 项目 ID - 技术设计

## Architecture And Ownership

- 数据所有权：`sys_tenant.roi_project_id`，类型 `VARCHAR(128)`、可空。可空仅用于兼容迁移前历史数据，应用写入契约对非默认工作空间要求非空。
- API 契约：`TenantDTO`、`TenantCreator`、`TenantEditor` 增加 `roi_project_id`。DTO 原样返回数据库值；SaaS 管理端创建/编辑模型在边界统一去除首尾空格并校验长度。
- 持久化：扩展现有 `create_tenant` / `update_tenant` 参数，在工作空间及三个绑定的同一事务中保存，不另建绑定表。
- UI：在 `Tenant.vue` 的 ROI 数据源选择框之后加入 `el-input`，创建/编辑共用；表单规则对非默认工作空间必填，默认工作空间禁用且不提交该字段。
- 国际化：四种现有语言增加“项目ID”、输入提示和必填提示。

## Data Flow

```text
管理端文本框
  -> TenantCreator / TenantEditor 校验与 trim
  -> create_tenant / update_tenant
  -> sys_tenant.roi_project_id
  -> TenantDTO
  -> 管理端编辑回显 / GET /system/tenant/current 消费
```

## Validation Contract

- SaaS 管理端创建/编辑非默认工作空间：缺失或 `null` 为 400；空字符串、纯空白或长度超过 128 为 422/校验错误。
- 默认工作空间：数据库允许空，API 禁止设置非空项目 ID；UI 禁用并不提交。
- 文本内容不做数字转换，不改变大小写，不移除内部空格，避免破坏外部系统标识。
- 编辑接口继续使用字段集区分“未提交字段”和显式值，但由于非默认工作空间为必填，完整编辑请求最终必须持有有效值；旧调用方缺失字段将收到明确错误，不提供静默兼容。

## Migration And Compatibility

- 新增 Alembic `157` 迁移，只添加/删除 `sys_tenant.roi_project_id`，不做数据回填或清理。
- 列保持可空，使已有记录和默认工作空间可无损升级；后续可在数据完整回填后单独评估数据库非空约束。
- `bound_project_id` 继续仅作为普通数据源 ID 的历史别名，不参与新字段读写。
- 既有用户自助申请/审批创建流程不采集该字段，继续允许创建空值记录；其后通过 SaaS 管理端编辑时必须补填。本次不扩展该申请产品流程。

## Transactions And Audit

- 创建/编辑仍只在路由末尾提交一次；项目 ID 与工作空间属性、普通数据源、ROI 数据源、第三方 MCP 绑定共同提交或回滚。
- 创建/更新审计 remark 增加 `roi_project_id`，编辑时明确记录实际值或默认工作空间的 `unchanged`，不写入额外隐私或凭据。

## Risks And Rollback

- 风险：旧的非默认工作空间缺值时无法直接保存其他修改。该行为符合本次必填要求，UI 会在保存前明确提示补填。
- 风险：项目 ID 可能包含审计分隔符；审计字段只用于可读记录，不用于反向解析。
- 回滚：回退前端/后端代码后，再执行迁移 downgrade 删除新增列；迁移不触碰其他业务数据。
