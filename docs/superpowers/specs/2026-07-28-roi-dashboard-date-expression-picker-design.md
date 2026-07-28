# ROI 看板日期表达式选择器设计

## 背景与目标

当前普通看板 SQL 编辑抽屉的“时间范围”使用简单下拉框和自定义日期范围，无法表达 ThinkingData 日期控件中的动态端点、静态端点和自然周期预设。目标是新增一个可复用的日期表达式选择器，并在首期只为“我的看板”中的目标 ROI 看板图表启用。

本功能不是看板全局日期筛选，也不替换图表卡片现有的“按天 / 按周 / 按月 / 选择时间”菜单。新组件只出现在 `DashboardSqlEditor.vue` 编辑抽屉的“时间范围”配置区，视觉风格与参考控件统一，保存仍沿用编辑抽屉现有流程。

## 已确认范围

### 本期包含

- 新建可复用组件 `DashboardDateExpressionPicker.vue`。
- 新建纯函数模块 `dashboardDateExpression.ts`，集中定义表达式、预设解析、校验和展示文本。
- 仅由 `DashboardSqlEditor.vue` 调用新组件。
- 通过图表配置 `sourceConfig.sql.builder.dateExpressionPickerEnabled === true` 显式启用。
- 首期只迁移当前“我的看板”中的目标 ROI 看板，资源 ID 为 `4f08e75945c3498486963e70f3c75688`。
- 支持动态/静态端点、自然周期、滚动窗口、固定起点到动态终点以及全部时间。
- 后端按 `Asia/Shanghai` 在每次执行时解析表达式，并把结果写入受控 SQL 日期参数。
- 迁移目标图表的固定日期条件，使每个物理表扫描都使用受控参数。

### 本期不包含

- 不修改 `frontend/src/views/dashboard/components/sq-view/index.vue`。
- 不修改图表卡片日期入口、粒度菜单、刷新逻辑或展示样式。
- 不增加看板全局日期筛选。
- 不按“ROI 看板”名称、业务字段名或固定看板 ID 在通用运行时代码中分支。
- 不自动迁移其他“我的看板”、推荐看板或历史 SQL。
- 不改变透视功能本身；目标图表仍可保持 `pivot.enabled = false`。
- 不增加无提示兼容回退；配置或表达式无效时不得退回 `30d`。

## 方案选择

### 采用方案：配置驱动的表达式组件与后端运行时解析

日期控件保存结构化表达式。前端负责编辑、校验和展示；后端负责按业务时区将表达式解析为确定的开始、结束自然日，再复用现有受控参数渲染、权限校验、只读执行和缓存链路。

该方案的优势是：自然周期语义不会在保存时固化；刷新或次日执行时会得到新的日期范围；通用代码不感知 ROI 业务；首期可通过一次性迁移精确控制启用范围。

### 未采用方案一：直接替换现有 `timeRange` 下拉框

现有下拉框仍适用于大量普通图表。全量替换会扩大回归面，也违反本期只针对目标 ROI 看板的范围。

### 未采用方案二：在图表卡片上新增日期控件

该方案会改动用户明确要求保留的卡片交互，并与已有“按天 / 按周 / 按月 / 选择时间”菜单职责重叠。

### 未采用方案三：保存时把预设换算成固定日期

“上周”“本月”“过去 30 天”等语义需要随执行日期变化。保存固定日期会使动态预设失去语义，必须保留结构化表达式并在后端运行时解析。

## 前端架构

### `frontend/src/views/dashboard/common/DashboardDateExpressionPicker.vue`

组件只负责日期表达式编辑，不读取路由、看板名称、资源 ID、数据源或 SQL。输入输出契约为：

```ts
type DashboardDateExpressionPickerProps = {
  modelValue: DashboardDateExpression | null
  disabled?: boolean
  timezone?: string
}

type DashboardDateExpressionPickerEmits = {
  'update:modelValue': [value: DashboardDateExpression]
  apply: [value: DashboardDateExpression]
  cancel: []
}
```

弹层采用参考控件的布局语言：顶部显示当前表达式名称和解析后的日期预览；左侧为预设列表；右侧分别编辑开始、结束端点；底部为取消和应用操作。控件使用 Element Plus 现有输入、日期选择、分段切换和弹层能力，不复制参考站点代码。

组件打开时从 `modelValue` 深拷贝内部草稿。端点、预设或日期变化只更新草稿；点击“应用”后才发出新表达式；点击“取消”、点击外部或关闭弹层均丢弃草稿。组件的“应用”只更新抽屉表单，不调用看板保存接口。

### `frontend/src/views/dashboard/common/dashboardDateExpression.ts`

纯函数模块承担以下职责：

- 定义 `DashboardDateExpression`、端点和预设类型。
- 规范化从持久化配置读出的表达式。
- 校验端点、数值和日期顺序。
- 生成编辑器展示文本与范围预览。
- 以显式 `now` 和 `timezone` 参数解析表达式，便于前后端共享测试用例。

模块不得依赖 Vue、DOM、路由或业务数据。

### `DashboardSqlEditor.vue` 集成

在现有“时间范围”区域保留时间字段与粒度选择。只有以下条件同时满足时，使用新组件替代该图表抽屉内的旧 `timeRange` 下拉与自定义日期输入：

```ts
sourceConfig.sql.builder.dateExpressionPickerEnabled === true
```

未启用图表继续使用现有控件和保存结构，行为不变。启用图表从 `sourceConfig.sql.builder.timeExpression` 恢复状态，应用草稿后更新抽屉内的 `sqlBuilder.timeExpression`。最终点击抽屉原有保存/应用按钮时，由既有 `writeEditorStateToViewInfo` 链统一持久化。

## 表达式模型

```ts
type DashboardDatePreset =
  | 'yesterday'
  | 'today'
  | 'previous_week'
  | 'current_week'
  | 'previous_month'
  | 'current_month'
  | 'past_7_days'
  | 'recent_7_days'
  | 'past_30_days'
  | 'recent_30_days'
  | 'past_90_days'
  | 'all_time'

type DashboardDateEndpoint =
  | { mode: 'dynamic'; unit: 'day'; offset: number }
  | { mode: 'static'; date: string }

type DashboardDateExpression =
  | { version: 1; mode: 'preset'; preset: DashboardDatePreset }
  | {
      version: 1
      mode: 'range'
      start: DashboardDateEndpoint
      end: DashboardDateEndpoint
    }
```

`offset` 以执行当天为 `0`，过去日期为负数。固定起点加动态终点示例：

```json
{
  "version": 1,
  "mode": "range",
  "start": { "mode": "static", "date": "2026-01-01" },
  "end": { "mode": "dynamic", "unit": "day", "offset": 0 }
}
```

自然周期必须保存为 `preset`，不能转换成当前日期偏移。预设语义如下：

| 预设 | 开始日期 | 结束日期 |
| --- | --- | --- |
| 昨日 | 执行日 - 1 天 | 执行日 - 1 天 |
| 今日 | 执行日 | 执行日 |
| 上周 | 上一个自然周周一 | 上一个自然周周日 |
| 本周 | 本周周一 | 执行日 |
| 上月 | 上一个自然月首日 | 上一个自然月末日 |
| 本月 | 当月首日 | 执行日 |
| 过去 7/30/90 天 | 执行日前 N 天 | 执行日前 1 天 |
| 最近 7/30 天 | 执行日前 N-1 天 | 执行日 |
| 全部时间 | `1000-01-01` | `9999-12-31` |

首期目标字段为 MySQL 数字型 `YYYYMMDD` 分区字段，因此“全部时间”使用 MySQL `DATE` 可表达域的上下界并渲染为 `10000101` 和 `99991231`。后续若把组件用于其他参数类型，必须先为对应数据源方言定义并测试合法上下界；不得沿用不兼容范围。

允许选择今日。今日尚无数据时查询返回空结果，这是合法结果，不禁用今日，也不自动改为昨日。

## 持久化配置

启用后的 Builder 配置示例：

```json
{
  "dateExpressionPickerEnabled": true,
  "timeField": "dt",
  "timeRange": "expression",
  "timeExpression": {
    "version": 1,
    "mode": "preset",
    "preset": "past_30_days"
  }
}
```

目标图表同时保存后端预览所需配置：

```json
{
  "enabled": false,
  "time_field": "dt",
  "range_enabled": true,
  "date_parameter_type": "yyyymmdd_number",
  "date_expression": {
    "version": 1,
    "mode": "preset",
    "preset": "past_30_days"
  }
}
```

`builder.timeExpression` 是编辑器配置，`pivot.date_expression` 是执行请求配置。抽屉保存时必须从同一份已校验草稿生成二者，避免两处语义漂移。读取时如两处同时存在但内容不一致，显示明确配置错误并禁止预览/保存，不能任选其一。

目标图表当前关闭透视。现有 `buildPivotConfig()` 在 `pivot.enabled = false` 时只返回 `{ "enabled": false }`，本功能必须调整这一边界：当日期表达式已启用时，即使透视关闭，也要保留 `time_field`、`range_enabled`、`date_parameter_type` 和 `date_expression`；只有透视专属的指标、分组和粒度配置继续受 `enabled` 控制。源数据预览与最终预览必须使用同一日期执行配置，不能因为关闭透视而绕过日期参数。

`builder.timeExpression` 是编辑态唯一来源，`pivot.date_expression` 由保存/预览适配函数从它派生，不允许两个控件分别编辑。持久化读回时的双份一致性校验用于发现历史数据或迁移错误。

## SQL 参数与执行链

目标看板当前 4 张 SQL 图表均使用固定的“21 天前至 1 天前”条件，且日期条件分散在多个 CTE 和物理表扫描中。迁移必须把每个相关物理扫描改为：

```sql
WHERE r.dt >= {{dashboard_start_yyyymmdd}}
  AND r.dt <= {{dashboard_end_yyyymmdd}}
```

不能只在最外层结果上过滤，否则会破坏分区裁剪，也无法扩大原 SQL 固定窗口。

执行顺序固定为：

1. 校验当前用户、租户、工作空间和数据源权限。
2. 校验表达式版本、预设、端点类型、静态日期和范围顺序。
3. 使用后端 `Asia/Shanghai` 当前时间解析开始、结束自然日。
4. 按 `date_parameter_type` 渲染受控日期字面量并替换 SQL 参数。
5. 对渲染后的最终 SQL 执行现有只读、表、字段和行权限校验。
6. 使用现有数据源执行链运行 SQL。
7. 使用包含表达式解析结果的缓存键读写结果缓存。

任何无效表达式、未知版本、未知预设、缺失端点或不完整参数对都必须阻断执行并返回明确错误。不得静默改用 `30d`、昨天或原 SQL 固定范围。

## 缓存与权限

现有预览缓存的租户、用户、数据源、SQL 和权限边界保持不变。缓存指纹额外包含：

- 表达式原始结构及版本。
- 解析后的开始日期和结束日期。
- `date_parameter_type`。
- 业务时区 `Asia/Shanghai`。

包含解析后日期可以保证动态预设跨日后不会命中前一天结果。权限校验必须先于缓存结果返回；无权用户不能通过旧缓存读取结果。

## 失败处理

- 表达式配置无效：编辑器显示字段级错误，禁止预览和抽屉保存。
- Builder 与 Pivot 表达式不一致：显示“日期表达式配置不一致”，禁止执行。
- SQL 日期参数缺失、不成对或类型不匹配：后端拒绝请求，不替换部分参数。
- SQL 解析或权限校验失败：沿用现有明确错误，不执行数据源查询。
- 数据源查询失败：保留抽屉草稿和上一次成功预览，允许用户修改后重试。
- 今日或其他合法范围无数据：返回成功空结果，不显示配置错误。
- 动态表达式跨日：下一次执行按新日期解析并使用新缓存键。
- 未启用图表：继续走现有 `timeRange` 路径，不做隐式格式升级。

## 测试范围

### 前端纯函数测试

- 所有预设在固定 `now`、`Asia/Shanghai` 下解析正确。
- “过去 N 天”不包含今日，“最近 N 天”包含今日。
- 上周、上月跨年边界正确。
- 静态端点、动态端点和固定起点到动态终点正确。
- 全部时间上下界符合首期 MySQL `YYYYMMDD` 契约。
- 未知版本、未知预设、非法日期、开始晚于结束被拒绝。
- 展示文本稳定且不依赖浏览器 UTC 截断。

### 前端组件与编辑器测试

- 未启用图表继续显示原时间范围控件。
- 仅显式启用图表显示新选择器，不读取看板名称或 ID。
- 打开弹层创建独立草稿；取消和外部关闭不修改表单。
- 点击组件“应用”只更新抽屉表单，不触发看板保存或图表卡片刷新。
- 抽屉最终保存同时写入一致的 Builder/Pivot 表达式。
- 恢复无效或不一致配置时显示错误且禁止预览/保存。
- 今日可选；无数据响应按成功空结果处理。
- 不导入或修改 `sq-view/index.vue` 的卡片日期逻辑。

### 后端测试

- 所有表达式类型按 `Asia/Shanghai` 解析正确。
- 参数渲染后执行既有只读、表、字段、行权限校验。
- SQL 注释和字符串中的伪参数不被替换。
- 参数缺失、不成对、混用或表达式无效时失败关闭。
- 不同租户、用户、数据源、表达式和解析日期的缓存隔离。
- 动态预设跨日后缓存指纹变化。
- 合法空结果正常返回。

### 集成与浏览器验证

- 在目标 ROI 看板打开 4 张图表的编辑抽屉，确认新控件可用且视觉统一。
- 修改草稿后取消，重新打开时原配置不变。
- 应用表达式并运行预览，确认最终 SQL 每个物理扫描均使用解析日期。
- 保存并重新打开抽屉，确认表达式语义完整恢复。
- 验证昨日、今日、上周、本月、过去 30 天和固定起点到今日。
- 确认图表卡片现有日期与粒度菜单没有代码或交互变化。

## ROI 配置迁移

目标资源 ID 只允许出现在一次性受控迁移工具或迁移清单中，不得进入组件、编辑器或后端通用运行时代码。

迁移对象为资源 `4f08e75945c3498486963e70f3c75688` 中当前盘点的 4 张 SQL 图表：

```text
2195201518565761024
2195202821815705600
2195203352126726144
2196527317097029632
```

迁移步骤：

1. 只读查询目标看板完整记录、4 张图配置和原始 SQL，输出迁移清单。
2. 在 `.codex-runtime` 下保存完整可回滚备份并计算 SHA-256；备份不得提交 Git。
3. 锁定资源 ID、租户、图表 ID、标题、原始 SQL 哈希和配置哈希；任一不匹配立即中止。
4. 将每个物理扫描中的固定日期条件替换为成对受控参数，并校验替换次数。
5. 写入启用标志、`timeField = dt`、`timeRange = expression`、结构化表达式和 Pivot 执行配置。
6. 在单个数据库事务内使用 `SELECT ... FOR UPDATE` 和旧值 CAS 校验更新；任一目标失败则整体回滚。
7. 提交后逐图读回，校验配置、SQL 参数、非目标字段和非目标图表哈希。
8. 对 4 张图分别执行只读预览，验证默认表达式、今日空结果和至少一个固定范围。
9. 浏览器验证编辑抽屉；若失败，使用备份按相同 CAS 边界恢复并再次读回。

迁移工具必须支持只读预演，默认不写库；只有显式 `--apply` 才允许更新。业务数据源始终只读。

## 验收标准

只有同时满足以下条件才可声明完成：

- 新选择器仅在显式启用的编辑抽屉中出现。
- 目标 ROI 看板 4 张图全部启用，其他看板和图表行为不变。
- 自然周期以语义表达式保存，跨日、跨周、跨月能重新解析。
- 今日可以选择，今日无数据返回成功空结果。
- 每个物理 SQL 扫描都使用受控日期参数。
- 权限、只读校验和缓存隔离得到自动化测试覆盖。
- 迁移具备完整备份、CAS 校验、逐图读回证据和可验证回滚路径。
- `sq-view/index.vue` 及图表卡片日期、粒度、刷新相关代码无变更。
- 前端定向测试、后端定向测试、生产构建和浏览器验收均通过。
