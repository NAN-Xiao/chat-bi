# 看板图表执行数据源单一事实来源修复设计

## 背景

普通看板资产归属于工作空间当前绑定的数据源，但单张 SQL 图表可以显式选择当前工作空间配置的绑定数据源或 ROI 数据源作为执行数据源。现有图表 JSON 同时保存：

- `viewInfo.datasource`
- `viewInfo.sourceConfig.sql.datasource`

这两个字段当前都表示 SQL 图表的执行数据源，却由不同代码路径读取和写入。看板复制、模板下发或历史数据迁移只更新其中一个字段时，会形成两个互相矛盾的数据源上下文。随后预览、编辑、刷新、混合来源执行和权限校验可能选择不同字段，最终产生错误 SQL 执行、错误 Schema 提示或跨工作空间上下文风险。

本次已确认的异常属于这种冲突：图表外层执行数据源被改为目标工作空间绑定数据源，`sourceConfig.sql.datasource` 和 SQL 本身仍保留来源工作空间的数据源上下文。目标 Schema 不包含 SQL 引用的物理表，因此共享 Schema 校验正确拒绝了查询。修复不能通过放宽 Schema 校验、允许跨空间数据源或静默回退解决。

## 目标

1. `viewInfo.datasource` 成为 SQL 图表执行数据源的唯一事实来源。
2. 停止写入并最终删除 `sourceConfig.sql.datasource`。
3. 普通 SQL、ROI SQL、SQL 与 MCP 混合来源图表使用同一数据源解析规则。
4. 保持现有 ROI 工作空间授权、表权限、字段权限和行权限边界不变。
5. 看板复制、移动、模板下发和发布不得只替换数据源 ID；必须验证目标数据源与 SQL 兼容。
6. 存量数据迁移可审计、可回滚、可重复执行，冲突数据不得自动猜测。

## 非目标

- 不改变工作空间一个绑定数据源的当前产品模型。
- 不把 ROI 数据源变成第二个普通绑定数据源。
- 不允许跨数据源 JOIN。
- 不根据看板名称、SQL 表名、数据源名称或业务领域推断执行数据源。
- 不放宽 `resolve_chart_execution_datasource` 的候选范围。
- 不绕过表、字段、JSON 子字段或行权限。
- 不为缺失表或不兼容 SQL 增加静默兼容回退。
- 不把来源工作空间的 SQL 自动改写成目标工作空间业务 SQL。

## 字段职责

修复后的职责固定如下：

| 层级 | 字段 | 职责 |
| --- | --- | --- |
| 看板 | `dashboard.datasource` | 看板资产归属数据源，也是新建 SQL 图表的默认候选 |
| 图表 | `viewInfo.datasource` | 当前 SQL 图表唯一的执行数据源，可为绑定数据源或当前空间 ROI 数据源 |
| SQL 来源 | `sourceConfig.sql.sql` | SQL 文本 |
| SQL 来源 | `sourceConfig.sql.builder` | SQL 构建器配置 |
| SQL 来源 | `sourceConfig.sql.lastResult` | SQL 来源最近一次结果快照 |
| SQL 来源 | `sourceConfig.sql.datasource` | 废弃并删除，不再读取或写入 |
| MCP 来源 | `sourceConfig.mcp.*` | MCP 服务、工具、参数和结果配置，与 SQL 执行数据源无关 |

目标 JSON：

```json
{
  "datasource": 8,
  "sql": "SELECT ...",
  "sourceConfig": {
    "sources": ["sql"],
    "mode": "sql",
    "primarySource": "sql",
    "sql": {
      "sql": "SELECT ...",
      "builder": {},
      "lastResult": {
        "fields": [],
        "data": []
      }
    }
  }
}
```

混合来源图表仍只有一个 SQL 执行数据源：

```text
viewInfo.datasource
  -> sourceConfig.sql.sql
  -> SQL 预览与执行

sourceConfig.mcp
  -> MCP 服务与工具
  -> MCP 执行

SQL 结果 + MCP 结果
  -> sourceConfig.merge
  -> 图表结果
```

## 统一读取规则

新增共享的图表执行数据源解析逻辑，前后端不得再各自使用 `a || b` 选择字段。

### 新格式

当 `viewInfo.datasource` 有有效值且 `sourceConfig.sql.datasource` 不存在时，直接使用外层值，并由后端执行当前空间候选校验。

### 历史重复格式

当两个字段都有值且相同：

- 运行期使用 `viewInfo.datasource`。
- 保存或迁移时删除 `sourceConfig.sql.datasource`。
- 不改变 SQL、Builder、图表配置或结果快照。

### 历史内层独有格式

当外层缺失、只有 `sourceConfig.sql.datasource`：

- 兼容期只把内层值作为迁移候选，不直接执行。
- 先调用后端受控入口确认该数据源是当前空间绑定数据源或 ROI 数据源。
- 再使用该数据源 Schema 校验 SQL 表范围。
- 全部通过后写入 `viewInfo.datasource` 并删除内层字段。
- 任一校验失败则标记为待修复，不回退到看板绑定数据源。

### 冲突格式

当两个字段都有值且不同：

- 返回 `dashboard_chart_datasource_conflict`。
- 禁止 SQL 预览、自动刷新、应用保存、报表解读、复制发布和缓存命中。
- 前端显示两个冲突 ID 对应的受控名称（仅限当前用户可见候选），要求重新选择执行数据源并重新预览。
- 不自动选择外层、内层、绑定数据源或 ROI 数据源。

### 两者缺失

- 已有图表加载时标记 `dashboard_chart_datasource_missing`，不执行 SQL。
- 新建图表可以在编辑器中预选当前绑定数据源，但只有用户成功预览并保存后才持久化。
- 服务端不能在保存或后台刷新时静默补值。

## 写入规则

### 前端

`DashboardSqlEditor` 保存时：

1. 只把选择结果写入 `viewInfo.datasource`。
2. `sourceConfig.sql` 不再写入 `datasource`。
3. 执行数据源继续进入预览签名；数据源变化必须使已有预览失效。
4. 切换数据源继续清空 SQL、字段映射、轴、系列、透视配置、Builder 状态和结果快照，并要求重新预览。
5. 已保存数据源不在当前空间候选集时清空选择并显示错误，不替换成绑定数据源。

`mixedChartData.ts` 等混合来源代码只读取 `viewInfo.datasource`，禁止继续使用：

```ts
sourceConfig.sql.datasource || viewInfo.datasource
```

### 后端

所有看板保存入口在持久化前执行统一规范化与校验：

1. 解析图表来源类型。
2. SQL 来源存在时要求有效的 `viewInfo.datasource`。
3. 调用 `resolve_chart_execution_datasource` 重新确认当前认证空间候选范围。
4. 如果请求仍携带内层字段：
   - 与外层相同：删除内层字段后保存。
   - 与外层不同：返回 `dashboard_chart_datasource_conflict`，拒绝保存。
5. SQL 文本或执行数据源变化后，旧预览签名和旧 SQL 结果不能证明当前配置可用。

旧客户端不能通过提交双字段继续制造冲突数据。

## ROI 权限边界

删除重复字段不改变 ROI 授权模型。执行链保持：

```text
viewInfo.datasource
  -> resolve_chart_execution_datasource
  -> 当前空间绑定数据源或有效 ROI 数据源
  -> validate_user_query_sql_or_raise
  -> 表、字段、JSON 子字段与行权限
  -> 只读 SQL 安全校验
  -> execute_user_query
```

约束如下：

- `datasource_access_checked=True` 只表示上游已确认数据源属于当前工作空间允许的执行候选。
- 该标志只跳过重复的通用数据源可见性检查。
- `apply_user_permission_scope` 必须保持 `True`。
- ROI 图表仍执行表禁止、字段禁止、JSON 子字段禁止和行权限。
- ROI 数据源被解绑、禁用或删除时，已有图表明确失败，不回退到绑定数据源。
- 缓存键继续包含租户、用户权限范围、实际执行数据源、SQL 和相关图表配置。

## 看板资产归属与图表执行

必须继续区分：

| 行为 | 使用的数据源 |
| --- | --- |
| 加载目标看板树、移动目标、看板资产归属 | `dashboard.datasource` |
| SQL Schema、预览、刷新、报表解读 | `viewInfo.datasource` |
| SQL + MCP 混合图表的 SQL 部分 | `viewInfo.datasource` |
| MCP 部分 | `sourceConfig.mcp` 对应的受控 MCP 上下文 |

不得用 ROI 图表执行数据源替代看板资产归属数据源，也不得用看板绑定数据源覆盖显式 ROI 图表执行数据源。

## 复制、模板下发与发布

当前“复制画布并统一覆盖每个图表 datasource”的方式必须废止。新流程按图表处理：

1. 读取来源图表唯一执行数据源及其受控角色：`bound` 或 `roi`。
2. 在目标空间解析相同角色的数据源：
   - `bound` 对应目标空间绑定数据源。
   - `roi` 对应目标空间有效 ROI 数据源。
3. 目标空间缺少对应角色时阻止该图表发布。
4. 使用目标数据源的方言和当前 Schema 解析 SQL。
5. 校验全部物理表存在且属于允许范围。
6. 校验 SQL 字段和权限范围。
7. 只有校验通过，且 SQL 的业务语义明确适用于目标数据源时，才允许发布。

通用平台不能根据相似表名自动改写 SQL。来源与目标 Schema 不兼容时，应由目标数据源的 Data Skills、元数据和明确配置重新生成 SQL，或者取消发布该图表。

交付任务必须保存逐图校验结果，包括：

- 来源图表 ID。
- 来源执行数据源角色。
- 目标执行数据源 ID 和角色。
- SQL 哈希。
- 解析状态。
- 物理表范围校验状态。
- 权限校验状态。
- 最终是否允许发布及明确原因。

任一 SQL 图表未通过时，整张看板默认不发布；除非产品明确支持并展示“部分不可用看板”，本修复不引入该行为。

## 存量数据审计与迁移

新增定向工具，默认只读，显式传入 `--apply` 才允许修改系统数据库。工具不得执行业务数据 SQL，只解析看板 JSON、候选数据源、Schema 元数据和权限范围。

### 分类

每张 SQL 图表必须归入且只归入以下一种状态：

| 状态 | 条件 | 自动处理 |
| --- | --- | --- |
| `clean` | 只有有效外层字段 | 无修改 |
| `duplicate` | 内外字段相同 | 删除内层字段 |
| `legacy_only` | 只有内层字段 | 校验通过后迁到外层 |
| `conflict` | 内外字段不同 | 禁止自动选择 |
| `missing` | 两者都缺失 | 要求重新选择 |
| `unavailable` | 数据源不属于当前空间候选 | 要求重新配置 |
| `schema_mismatch` | SQL 物理表不属于目标 Schema | 重新生成 SQL 或取消发布 |
| `parse_error` | SQL 无法按数据源方言解析 | 人工修复 SQL |

一个图表可以同时附带问题标签，例如 `conflict + schema_mismatch`，但迁移主状态必须唯一，以便统计和幂等处理。

### 写入安全

迁移工具必须：

1. 支持按租户、看板 ID 和状态过滤。
2. 输出看板、图表、内外数据源、候选角色、SQL 哈希和校验结果，不输出连接凭据。
3. 写入前备份目标看板完整原始行及 JSON 哈希。
4. 使用 PostgreSQL advisory transaction lock。
5. 以原 `canvas_view_info` 和 `update_time` 作为 CAS 条件。
6. 任一目标行未精确更新一次则回滚。
7. 事务内读回验证后再提交。
8. 重复执行时保持幂等。
9. 提供使用备份和新旧哈希校验的恢复入口。

### 当前异常处理原则

对于外层绑定到目标空间普通数据源、内层仍指向来源 ROI 数据源、SQL 又引用来源 Schema 的看板：

- 不允许简单删除内层字段后继续执行。
- 不允许简单把外层改回来源数据源，因为来源数据源不一定属于当前工作空间授权上下文。
- 目标空间已配置合法 ROI 数据源时，应在该数据源的语义配置和 Schema 上重新生成并验证 SQL。
- 目标空间没有相关 ROI 数据时，应取消发布对应推荐看板或图表。

## 分阶段上线

### 第一阶段：冲突可见与阻断

- 增加统一解析函数和错误类型。
- 后端保存、预览、刷新和报表解读阻断冲突。
- 前端明确展示冲突，不静默选值。
- 保留历史内层字段的只读识别能力。

### 第二阶段：停止双写

- 前端停止写入 `sourceConfig.sql.datasource`。
- 后端规范化相同的重复字段并拒绝不同值。
- 混合来源执行改为只读 `viewInfo.datasource`。
- 修复复制、模板下发和发布前校验。

### 第三阶段：只读审计

- 全库扫描并输出各状态数量和目标清单。
- 单独复核 `conflict`、`unavailable`、`schema_mismatch`。
- 未确认报告前不写存量数据。

### 第四阶段：迁移与业务修复

- 自动处理 `duplicate`。
- 对验证通过的 `legacy_only` 执行迁移。
- 对冲突或 Schema 不匹配看板重新生成 SQL、重新配置 ROI 数据源或取消发布。
- 执行迁移后再次全库扫描，证明不存在新增冲突。

### 第五阶段：删除兼容读取

- 确认生产数据不再存在 `legacy_only`。
- 删除对 `sourceConfig.sql.datasource` 的读取、类型定义和测试夹具。
- 保留服务端对旧客户端提交该字段的冲突拒绝一段发布周期；确认旧客户端退出后再删除请求兼容代码。

## 测试策略

### 前端

- 普通 SQL 图表只保存外层数据源。
- ROI SQL 图表重新打开后恢复外层数据源。
- 混合来源图表 SQL 部分只读取外层数据源，MCP 部分不受影响。
- 内外相同历史数据可打开并在保存后清理内层字段。
- 内外冲突时禁止预览和保存，并显示明确错误。
- 数据源不属于当前空间时不回退到绑定数据源。
- 切换数据源后旧 SQL、字段映射和预览全部失效。

### 后端

- 候选集仍只包含当前空间绑定数据源和有效 ROI 数据源。
- `viewInfo.datasource` 为 ROI 数据源时预览、保存、刷新和报表解读使用同一 ID。
- ROI 路径仍应用表、字段、JSON 子字段和行权限。
- 请求携带相同内外字段时规范化成功。
- 请求携带冲突字段时所有写入口拒绝。
- 缺少执行数据源时不自动补看板绑定数据源。
- Schema 不兼容时发布失败，不修改 SQL 或数据源。
- 复制普通图表映射到目标绑定源；复制 ROI 图表只映射到目标 ROI 源。
- 目标空间无 ROI 源时发布失败。

### 迁移工具

- 七类状态识别准确。
- CTE、派生表和限定 Schema 表的物理表提取正确。
- 默认只读。
- `--apply` 只处理允许自动迁移的状态。
- CAS 冲突、锁失败、读回不一致时整体回滚。
- 备份恢复和重复执行通过。

### 回归范围

- SQL 图表编辑器。
- 看板加载和自动刷新。
- ROI 执行数据源权限。
- 混合 SQL + MCP 图表。
- 图表移动和复制。
- 平台模板复制与工作空间下发。
- 报表解读。
- 看板缓存隔离。

## 验收标准

1. 新保存的看板 JSON 不再包含 `sourceConfig.sql.datasource`。
2. 所有 SQL 执行入口只使用 `viewInfo.datasource`。
3. 内外冲突不会触发任何 SQL 执行或缓存返回。
4. ROI 图表继续使用当前空间 ROI 数据源，且表、字段和行权限全部生效。
5. ROI 数据源失效时明确失败，不回退到绑定数据源。
6. 看板复制和发布不会仅替换数据源 ID 后保留不兼容 SQL。
7. 存量自动迁移只处理可证明无歧义的记录，冲突记录均有明确处置结果。
8. 迁移前后都有完整备份、哈希、逐图审计和可验证恢复路径。
9. 全库复扫不再存在内外冲突，且没有新增跨工作空间数据源引用。

## 与既有设计的关系

本文延续以下既有约束：

- `2026-07-23-dashboard-chart-execution-datasource-design.md` 定义的当前空间绑定源/ROI 源候选模型。
- `2026-07-31-dashboard-roi-permission-scope-design.md` 定义的 ROI 数据源预校验不绕过用户权限范围。
- `2026-07-30-dashboard-roi-chart-move-target-design.md` 定义的看板资产归属与图表执行数据源分离。

本文替代早期实现或计划中同时写入 `viewInfo.datasource` 与 `sourceConfig.sql.datasource` 的做法。后续文档、迁移脚本和测试应以 `viewInfo.datasource` 为唯一执行数据源字段。

## 2026-08-13 定点修复记录

资源 `dcb7645772724045bf3097811b2e9a14`（空间 `7493583885482070016`）的 5 张 ROI 图表已完成受控修复：

- 看板资产数据源保持 `9`，不改变资产归属。
- 图表执行数据源从冲突的外层 `9` / 旧内层 `8` 迁移为唯一外层 `16`（`ROI_unicorn`）。
- 修复前确认空间当前 ROI 配置为 `16`，来源 `8` 与目标 `16` 的 8 张物理表一致，5 条 SQL 的物理表均被目标 Schema 覆盖。
- SQL 文本及 5 个 SQL SHA-256 保持不变，只修改执行上下文并删除旧内层字段。
- 使用 `tools/repair_unicorn_roi_dashboard_datasource.py` 的固定资源、租户、图表 ID、SQL 哈希、事务锁、画布与更新时间 CAS、备份及读回校验执行。
- 写后全库复扫从 `clean=358/conflict=55` 变为 `clean=363/conflict=50`；`duplicate=354/legacy_only=5/missing=101` 未变化。
- 备份位于 `.codex-runtime/dashboard-datasource-backups`，脚本的 `--restore <backup>` 仅在当前画布仍等于本次修复结果时允许恢复。

### unicorn 普通看板残留冲突清理

空间 `7493583885482070016`（`WSWGCD2XXN`，`unicorn`）的 9 个普通看板、50 张 SQL 图表已完成受控清理：

- 50 张图表均为外层 `viewInfo.datasource=9`、旧内层 `sourceConfig.sql.datasource=6`；空间当前唯一绑定数据源为 `9`，数据源 `6` 属于其他空间。
- 修复前按 MySQL 方言解析全部 SQL，引用的物理表仅为 `event`、`event_realtime`、`user`，均被目标数据源 `9` 的可用 Schema 覆盖。
- 保留唯一执行数据源 `viewInfo.datasource=9`，只删除残留的旧内层字段；看板资产数据源、SQL 和其他图表配置均未修改。
- 使用 `tools/repair_unicorn_dashboard_datasource_conflicts.py` 的固定空间、看板和图表集合校验、事务锁、画布与更新时间 CAS、备份及读回校验执行。
- 写后复扫确认 `unicorn` 的 55 张 SQL 图表全部为 `clean`：50 张普通图表使用数据源 `9`，5 张 ROI 图表使用数据源 `16`；全库 `conflict` 从 `50` 变为 `0`。
- 备份位于 `.codex-runtime/dashboard-datasource-backups`，脚本的 `--restore <backup>` 仅在 9 个看板仍等于本次修复结果时允许恢复。

### gig、j2000、lds 看板数据源修复

用户所称 `j200` 在系统中唯一匹配的启用空间为 `j2000`（`WSCWXDWV48`）。三个空间共 30 个看板、165 张 SQL 图表已完成受控修复：

- 修复前每个空间均有 55 张图表重复保存同一个内外数据源；其中 50 张普通图表应使用空间绑定源，5 张 ROI 图表实际需要使用空间配置的 ROI 源。
- 普通图表保留空间绑定源：`gig=12`、`j2000=11`、`lds=10`；ROI 图表分别改为 `gig=13`、`j2000=15`、`lds=14`。
- 三个 ROI 数据源均为有效配置，且各自的 8 张可用物理表完整覆盖 5 条 ROI SQL；普通图表引用的 `event`、`event_realtime`、`user` 也被各自绑定源完整覆盖。
- 所有目标图表均删除旧内层 `sourceConfig.sql.datasource`；看板资产数据源、SQL 和其他图表配置未修改。
- 使用 `tools/repair_gig_j2000_lds_dashboard_datasources.py` 的固定空间与看板集合、角色校验、Schema 校验、事务锁、画布与更新时间 CAS、备份及读回校验执行。
- 写后复扫确认三个空间各有 55 张 `clean` 图表，无 `conflict`、`duplicate`、`legacy_only` 或 `missing`；全库 `duplicate` 从 `354` 降为 `189`，`conflict` 保持为 `0`。
- 备份位于 `.codex-runtime/dashboard-datasource-backups`，脚本的 `--restore <backup>` 仅在 30 个看板仍等于本次修复结果时允许恢复。
