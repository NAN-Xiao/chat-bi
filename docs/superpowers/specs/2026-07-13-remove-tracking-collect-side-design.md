# 移除事件采集端设计

## 背景

当前工作空间数据字典在“事件参数对照”中暴露“采集端”列，并把该值保存为事件映射 JSON 的 `collect_side` 字段。该字段没有实际分析用途，却同时进入事件目录 API、前端 SQL 构建器元数据和 LLM tracking 语义上下文，增加了维护成本。

本次按产品决定彻底移除采集端语义。新导出不再包含该列；历史 Excel 仍允许导入，但采集端内容被静默忽略。

## 目标

- “事件参数对照”固定从 10 列缩减为 9 列，移除“采集端”。
- tracking 配置保存、读取和 LLM 上下文中不再出现 `collect_side` 或 `collectSide`。
- 事件目录 API 和前端 SQL 构建器不再暴露采集端属性。
- 历史 Excel 中的“采集端”列保持可导入，但其值不保存、不回显。
- 清理数据库中已经存在的采集端 JSON 键。

## 非目标

- 不修改事件名称、事件显示名、事件标签、事件参数或事件分组。
- 不改变“事件参数对照”的事件合并、参数展开和排序规则。
- 不根据采集端值推导其他字段，也不把采集端迁移到扩展属性。
- 不在本次代码实施中自动执行共享数据库迁移。

## 方案

### Excel 导出

从 `EVENT_PARAMETER_MAPPING_COLUMNS` 及相关导出行结构中删除 `collect_side`。新表头顺序为：

1. 事件名（必填）
2. 事件显示名
3. 事件说明
4. 事件标签
5. 数据源字段
6. 属性名（必填）
7. 属性显示名
8. 属性类型（必填）
9. 属性说明

事件合并判断不再包含采集端，仅使用事件名、事件显示名、事件说明和事件标签。正常 First Zombie 字典导出后，“事件参数对照”应保持 756 行，范围从 `A1:J756` 变为 `A1:I756`。

### 历史 Excel 导入

保留“采集端”和 `collectside` 的表头别名识别，将规范化后的 `collect_side` 归入已废弃、忽略列集合。解析器不再把该值写入事件映射，也不把它保存到 `extra_properties`。

因此历史文件仍可导入，但采集端值会被有意静默丢弃；再次导出时不再出现该列。

### 配置读写与 LLM 上下文

新增统一事件映射清理函数，对 `event_name_mappings` 中每个对象的顶层 `collect_side` 和 `collectSide` 键进行删除：

- `_config_dto` 在读取数据库时清理，避免迁移尚未执行时旧值进入 API 和 LLM 上下文。
- `save_tracking_config` 在写入数据库前清理，防止 API 客户端重新写回旧字段。
- Excel 导入构造的事件映射不再产生该字段。

tracking prompt 使用清理后的 DTO，因此无需单独增加 Prompt 过滤分支。

### 事件目录与前端

- 从 `TenantTrackingEventCatalogItem` 删除 `collect_side`。
- 后端 `build_tracking_event_catalog` 不再读取或返回采集端。
- 前端 `TrackingEventCatalogItem`、`SchemaFieldOption` 和事件选项构造逻辑删除 `collect_side/collectSide`。
- SQL 构建器的事件选择、事件参数选择和 SQL 生成逻辑保持不变。

### 数据迁移

新增 Alembic 迁移：

- revision：`143trackingcollectside`
- down revision：`142trackinggroups`
- 对 `sys_tenant_tracking_config.event_name_mappings` 的 JSON 数组逐项处理。
- 仅当数组元素为对象时删除顶层 `collect_side` 和 `collectSide`，非对象元素原样保留，数组顺序不变。
- 不修改事件数量、参数结构、事件分组或其他 tracking 表。

该迁移是不可逆数据清理。`downgrade` 不恢复已删除的值，因为数据库中没有可靠来源重建这些字段。

## 错误与兼容行为

- 新 Excel 不生成采集端列。
- 旧 Excel 有采集端列时不报错、不告警，值直接忽略。
- API 请求携带 `collect_side/collectSide` 时，保存成功但字段被移除。
- 迁移执行前读取旧记录时，DTO 层仍保证不返回采集端。
- 非数组或异常事件映射沿用现有 JSON 容错行为，不因本次移除引入新的业务回退。

## 测试与验收

### 后端测试

- 导出表头严格等于 9 列且不包含“采集端”。
- 历史 10 列 Excel 可导入，导入结果不包含 `collect_side`。
- API 编辑器输入 `collect_side` 或 `collectSide` 后，持久化前被清理。
- 读取旧 JSON 时 DTO 不返回采集端。
- 事件目录 DTO 和序列化结果不包含 `collect_side`。
- Alembic 唯一 head 为 `143trackingcollectside`，迁移链指向 `142trackinggroups`。

### 前端测试

- TypeScript 类型与构造结果不再包含 `collect_side/collectSide`。
- 现有 SQL 构建器测试和类型检查通过。

### 真实 Excel 验收

- 使用已恢复的 163 个事件字典导出。
- “事件参数对照”范围为 `A1:I756`。
- 首事件仍为 `GVGBattleResult`，首参数仍为 `allianceId`。
- “事件分组”sheet 内容和行为不变。
- 视觉检查确认删除列后表头、合并区域和参数列没有错位或截断。

## 发布与恢复

- 代码发布前保留现有 PostgreSQL 完整备份。
- 部署时执行 Alembic `143trackingcollectside` 清理历史 JSON。
- 如需回退应用版本，旧代码能读取缺少采集端的事件映射；采集端值不会自动恢复。
- 本次实施不自动修改共享系统库，迁移执行由部署流程或用户单独确认。
