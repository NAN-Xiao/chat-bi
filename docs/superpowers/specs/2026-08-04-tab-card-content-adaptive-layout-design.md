# Tab 卡片内容单向自适应设计

## 背景

看板的 `SQTab` 内部同时支持编辑画布和预览画布。Tab 内卡片的物理宽高由各自画布根据 `sizeX`、`sizeY`、矩阵行列数和网格间距换算，因此编辑页与 Tab 预览页中的像素尺寸可以不同。

卡片内容需要根据当前实际空间调整摘要布局、信息密度和图表尺寸，但不能让内容尺寸反向修改 Tab 卡片外框。历史实现曾以 `.chart-show-area` 的内部剩余尺寸作为布局输入，而布局输出又改变 padding、标题高度和摘要 DOM，最终形成：

```text
chart-show-area 尺寸
  -> frameSize
  -> layout / density / show
  -> padding / header / 摘要结构变化
  -> chart-show-area 尺寸变化
  -> ResizeObserver
  -> 重绘
  -> 再次测量
```

本设计只解决 Tab 内 `SQView` 卡片的内容自适应和稳定性，不改变 Tab 网格尺寸。

## 目标

1. Tab 卡片外框由 Tab 网格单向分配，`SQView` 不修改 `sizeX`、`sizeY` 或父级布局。
2. 编辑页和 Tab 预览页分别根据各自真实 Card 根边界调整内部展示，不要求像素尺寸一致。
3. 图表类型、摘要开关、轴配置和真实外部 Card 尺寸变化后，内部布局可以重新计算并稳定收敛。
4. 普通数据请求不得通过尺寸回写触发布局循环；数据结构确实改变布局资格时最多产生一次内容布局迁移。
5. 保持当前通用 BI 行为，不增加数据源、业务字段、图表问题或看板 ID 特例。
6. 每个有效布局输入签名只执行一次内容策略计算；摘要变化后只允许当前图表实例原地 resize/render 一次。

## 非目标

- 不实现内容驱动的 Tab Card 自动增高。
- 不统一编辑页和 Tab 预览页的物理像素尺寸。
- 不在预览或运行时持久化新的 `sizeX`、`sizeY`。
- 不通过锁死首次布局、隐藏全部摘要、吞掉 `ResizeObserver` 告警或延长 debounce 掩盖问题。
- 不修改摘要统计口径、图表字段映射、SQL、数据刷新和权限逻辑。

## 方案选择

### 方案 A：稳定外框驱动内部自适应（采用）

Tab 网格分配 Card 根边界，卡片根据根 `border-box` 计算规范帧，再决定内部 `layout`、`density`、`show` 和 `maxStats`。内部输出不回写 Card 或网格。

优点是尺寸所有权清晰、现有图表策略可复用，并且能从结构上断开反馈环。代价是需要明确传播 Tab 渲染上下文，并补充真实 DOM 稳定性测试。

### 方案 B：仅使用 CSS Container Query

CSS 可以根据 Card 宽度调整字号和显隐，但摘要统计项数量、top/side 策略、数据相关布局资格和图表库 resize 仍需要 JavaScript。该方案会把一套策略拆成 CSS 与 TypeScript 两份，边界难以保持一致，因此不采用。

### 方案 C：子卡片向 Tab 网格申请高度

该方案可以让外框随内容增长，但会移动 Tab 内其他卡片，并重新建立“子内容变化 -> 父尺寸变化 -> 子内容变化”的回写路径，与本次目标冲突，因此不采用。

## 尺寸所有权

### Tab 网格

Tab 编辑器和 Tab 预览器是 Card 外框尺寸的唯一生产者。它们继续使用各自的矩阵参数、单元格尺寸和间距，将持久化的 `sizeX`、`sizeY` 单向映射为 Card 像素边界。

Tab 网格可以因为用户拖拽、Tab 容器变化或页面响应式布局产生新的 Card 根边界，但不接收来自 `SQView`、摘要组件或图表组件的尺寸写入。

### SQView

`SQView` 是内容布局策略的所有者。在 `dashboardLayoutSurface='tab'` 时，Card 根 `border-box` 是唯一几何观察源；日期和透视工具栏使用显式配置派生的固定 reserve，不读取工具栏实时 DOM 高度，也不给工具栏挂尺寸观察器。`SQView` 不得观察 `.chart-show-area` 作为策略输入，也不得从尺寸观察回调调度父级或网格重排。

### ChartComponent

`ChartComponent` 只消费最终分配到的图表挂载区域。实际宽高发生变化时，它可以调用图表库 render/resize，但不能修改 Card 根边界、`frameSize` 或网格坐标。

## 显式 Tab 上下文

当前 Tab 预览链路中的 `inTab` 只用于 `SQPreview` 网格间距和 `frameless` 外观；Tab 编辑链路中的 `inTab` 只形成编辑器 CSS class。`SQView` 不能从现有 props 明确判断自己是否位于 Tab 内。

新增内部布局上下文 `dashboardLayoutSurface`：

```ts
type DashboardLayoutSurface = 'main' | 'tab'
```

上下文必须沿组件所有权链显式传播：

```text
Tab 预览：SQTab -> SQPreview -> SQComponentWrapper -> SQView
Tab 编辑：SQTab -> DashboardEditor -> CanvasCore -> 动态 SQView
主画布：DashboardEditor / SQPreview -> SQView(surface = main)
```

不得根据 `frameless`、DOM class、canvas ID 命名或父节点查询推断 Tab 上下文。`dashboardLayoutSurface` 仅表达布局宿主，不承载业务含义，也不改变数据访问、权限或图表口径。

`dashboardLayoutSurface='tab'` 启用本设计的根框驱动、固定 reserve 和单次状态转换路径；`main` 是默认值并保留现有主画布行为。本次不得仅传播 surface 而继续让 Tab 与 main 进入同一隐式分支。

现有 `showPosition` 继续区分 dashboard 与 `multiplexing`；`dashboardLayoutSurface` 只在 dashboard 分支内区分 Tab 和 main，不替代 `showPosition`。

## 单向数据流

Tab 卡片内容自适应使用以下单向流程：

```text
Tab Card 根 border-box 或明确结构配置真实变化
  -> 根据显式工具栏 variant 取得固定 reserve
  -> 生成 compact 基准规范帧并按整数像素去重
  -> 为规范帧、图表结构和摘要配置生成布局输入签名
  -> 每个有效输入签名执行一次 resolveInsightDisplay(frame, chart config, layout history)
  -> 应用摘要 layout / density / show / maxStats
  -> 保持 ChartComponent key 和实例稳定，在最终剩余空间内原地 resize/render 一次
  -> 结束，不回写 Card 或 Tab 网格
```

规范帧继续按稳定外边界计算：

```text
规范宽度
  = Card 根 border-box 宽度
  - 根边框
  - compact 基准水平 padding

规范高度
  = Card 根 border-box 高度
  - 根边框
  - compact 基准垂直 padding
  - compact 基准标题高度和标题间距
  - 显式工具栏 variant 对应的固定 block reserve
```

Tab 工具栏 variant 只有 `none`、`pivot`、`date`、`combined` 四种，由摘要策略之外的日期和透视配置直接产生。固定 reserve 分别为 `0px`、`30px`、`36px`、`36px`；Tab 的 combined 工具栏保持单行并在固定 reserve 内做内部溢出裁剪，不允许内容换行扩大占用。

布局输出可以改变当前实际 padding、摘要 DOM、工具栏内部显隐和图表剩余空间，但不能改变上述规范帧的输入，也不能触发再次测量。相同 Card 根边界和相同显式工具栏 variant 只能得到同一个规范帧。

## 触发规则

### 允许触发内容策略重新计算

- Tab 首次挂载或从隐藏状态恢复为正尺寸。
- Tab 容器或 Card 外框发生真实 resize。
- 用户在编辑器中改变 Card 的 `sizeX` 或 `sizeY`。
- 图表类型、X/Y/series 配置或摘要开关发生变化。
- 日期、透视等稳定工具栏的明确组成配置改变工具栏 variant。

### 不得作为尺寸策略触发源

- `.chart-show-area`、`.chart-container` 或图表 canvas/SVG 的内部尺寸变化。
- 稳定工具栏的实时 DOM 高度、`ResizeObserver` 回调或布局策略导致的内部显隐变化。
- 图表库一次 render/resize 完成事件。
- 请求 ID、刷新时间、加载进度或普通数据值变化。
- 摘要组件内部减少统计项或缩放内容的结果。

普通数据值、请求状态、请求 ID 和刷新时间变化不进入布局输入签名，也不重新执行内容布局策略。签名包含整数规范帧、图表 ID/type、X/Y/series 字段身份、规范化摘要配置、工具栏 variant，以及现有策略实际消费的纯数据结构资格，例如 series 分组是否跨越策略阈值、时间轴 granularity。只有这些结构输入变化时才生成新签名，并针对该签名计算一次；数据结构确实跨越布局资格时允许发生一次内容迁移，但仍不得更新外框或再次形成尺寸输入。

摘要显隐、layout 或 density 改变后，最终图表容器可以产生一次真实尺寸变化，并触发当前 `ChartComponent` 实例原地 resize/render 一次。该容器变化不得重新进入内容布局策略，也不得通过版本号或 Vue `key` 卸载重建图表组件。

数据响应包含新图表数据时，仍允许同一 `ChartComponent` 实例执行正常的一次数据渲染；它与内容布局转换是两条独立单向链。普通请求不得因此重新计算 layout/density/show/maxStats、修改 key 或卸载重建 Vue 组件。

## 去重与状态

### 规范帧去重

`frameSize` 只在规范宽高的整数像素值真正变化时更新。相同输入直接返回，不触发后续策略计算或图表重绘。

### 布局签名去重

Tab 路径保存 `lastProcessedLayoutSignature` 和上一份稳定 `insightDisplay`。当前签名与上一连续处理签名相同时直接复用稳定结果；签名变化时执行一次显式状态转换，成功后原子更新签名、`previousLayout`、`previousDensity` 和稳定结果。

签名去重不是生命周期 Map 缓存。`A -> B -> A` 中最后一个 `A` 必须结合当时的迟滞历史重新计算；普通数据请求产生相同连续签名时则不计算。现有在 Vue `computed` 求值过程中写入 `previousLayout`、`previousDensity` 的副作用应由显式状态转换替代。

### 布局历史

保留 `previousLayout` 与 `previousDensity`，只用于真实外部 resize 在阈值附近的迟滞。图表 ID、类型和轴结构变化时重置历史。

不得恢复 `previousShow` 跨轴显隐历史，也不得使用历史状态覆盖当前明确的摘要配置。

### 图表身份

Card resize、摘要显隐和密度变化不能改变 `ChartComponent` 的 Vue `key`。Vue `ChartComponent` 实例保持挂载，只在真实图表容器尺寸或数据配置变化时更新。本设计中的“原实例”专指 Vue 组件实例；图表库内部继续使用现有原子渲染层切换机制，不纳入本次改造。

同一次有效布局输入只允许产生一次摘要 DOM 迁移，以及至多一次由最终容器尺寸变化引起的原地图表 resize/render。不得通过递增版本号、重复 `nextTick` 或 `setTimeout` 重新挂载或反复调度图表。

## 摘要行为

- 明确关闭摘要时由 `SQView` 直接不挂载 `ChartInsightHeader`，不能只在子组件内部返回空 DOM。
- 开启摘要时，根据固定 Card 空间选择 top/side、regular/compact/mini/basic、统计项上限和必要的内容缩放。
- 空间低于现有通用可读下界时，可以按当前策略隐藏摘要，把空间留给图表；不通过增高 Card 强制展示。
- `ChartInsightHeader` 的 side fit 只能减少内部统计项或缩放内部内容，不能改变 Card 根边界或策略规范帧。

## Tab 生命周期

非活动 Tab 可能具有零尺寸或不可见 DOM。初始无有效规范帧时保持 `unmeasured`，不写入伪造尺寸；摘要暂不挂载，图表等待有效空间。Tab 激活后，根 `border-box` 的有效变化触发一次测量并进入正常策略。

从有效尺寸变为零尺寸时保留上一份有效规范帧，不用零尺寸覆盖；再次显示后只在新规范帧不同的情况下更新。

## 错误处理

- compact CSS 基准缺失、不可解析或计算结果非正数时，不回退到 `.chart-show-area` 或任意子节点尺寸。
- 失败时保留上一份稳定布局状态；不写入 `frameSize`，不修改 `ChartComponent` 的 Vue `key`。首次测量失败则保持 `unmeasured`。
- 失败路径不得使用 `nextTick`、`setTimeout` 或等价定时任务自重试。后续只接受新的合法外部触发，例如 Card 根边界真实变化、Tab 重新激活或图表结构配置变化。
- 同一测量错误只输出一次明确开发诊断，避免日志循环。
- `ResizeObserver loop` 告警不得被捕获后静默忽略，出现时视为回归失败。

## 测试设计

### 上下文传播契约

覆盖 Tab 编辑和 Tab 预览两条链路，断言 `dashboardLayoutSurface='tab'` 最终传入 Tab 内 `SQView`；主画布显式传入 `main`。不得用 `frameless` 或 DOM 查询代替。

### 策略与闭环回归

对不同固定 Tab Card 根尺寸扫描以下场景，并要求在有限步内收敛：

- 摘要开启与关闭。
- line、area、column、bar、pie、funnel、table、metric、sankey、treemap。
- 单指标、多指标和多 series。
- top/side 及 regular/compact/mini/basic 边界上下一个像素。
- 编辑页与 Tab 预览页不同物理尺寸。

测试必须证明策略输出不会改变规范帧输入，且 `SQView` 路径不存在 `sizeX`、`sizeY` 写入。

### 组件结构契约

断言：

- Tab 模式的 `SQView` 只观察 Card 根节点的 `border-box`；工具栏 reserve 只由显式 variant 决定，不读取或观察工具栏实时 DOM 高度。
- `SQView` 不观察 `.chart-show-area`。
- 尺寸观察回调不调用 `scheduleRenderChart()` 或网格 resize API。
- Tab 使用显式状态转换和连续签名去重，不在 Vue `computed` 求值中修改布局历史。
- `ChartComponent` key 在摘要和密度变化时保持稳定。
- `ChartComponent` 只在实际图表容器宽高变化时调度图表更新。
- 测量失败路径不写 `frameSize`、不修改组件 key，且不包含 `nextTick`、`setTimeout` 自重试。

### 真实 Tab DOM 回归

本次不新增 Playwright、Vitest 或 jsdom 依赖。自动化回归由纯协调器测试和源码结构契约承担；真实 DOM 稳定性通过现有本地四进程开发栈和应用内浏览器执行并记录验收结果。

在 Tab 编辑和 Tab 预览中分别固定外框，依次执行：

1. 开启和关闭摘要。
2. 在顶部摘要、侧边摘要和无摘要图表类型间切换。
3. 切换 Tab、隐藏后恢复、调整 Tab 容器和 Card 尺寸。
4. 对相同配置执行多次数据刷新。

每次合法操作完成后连续采样至少 3 秒，记录根宽高、density、layout、摘要存在状态、图表宽高、活动渲染层数量和 loading 状态。要求根边界不被内容修改，布局最多迁移一次后稳定，宽高波动不超过 1px，没有重复活动图层、loading 闪烁或 `ResizeObserver loop` 告警。

## 成功标准

1. Tab Card 的 `sizeX`、`sizeY` 在内容自适应期间保持不变。
2. 编辑页和 Tab 预览页可以得到不同 density/layout，但都在各自固定外框内稳定。
3. 摘要开关和图表类型变化后，内容最多发生一次布局迁移。
4. 同结构数据连续刷新不会触发尺寸策略迁移或组件重挂载。
5. 真实 Tab resize 后图表适配最终空间，停止操作后 3 秒内所有采样状态稳定。
6. 没有 `ResizeObserver loop`、重复 loading、持续 render 或 Card 网格回写。
7. 测量失败保留上一稳定状态，不写 `frameSize`、不修改图表 key，也不安排异步自重试。
