# 看板摘要布局反馈环全局稳定性设计

## 背景与目标

看板卡片在异步数据加载完成、摘要出现后，会在两套布局之间持续切换，表现为卡片内容、摘要和图表宽度反复跳动。录屏中的第一张折线图在 `1510x936` 视口下可稳定复现：卡片根容器约为 `1179x360`，内部区域在以下两个状态间每 `100~200ms` 循环：

- `1159x280`：顶部布局、`basic` 密度、摘要隐藏、图表宽度 `1159`；
- `1155x270`：侧边布局、`mini` 密度、摘要显示、图表宽度约 `969`。

本次目标不是修复某一个折线图或某一个高度阈值，而是消除看板摘要布局决策中的尺寸反馈环，使所有通过 `SQView` 展示的看板图表在异步加载、真实外部缩放和不同摘要形态下都能稳定。成功标准如下：

1. 相同的卡片外部 border box 和相同的工具栏有效 block contribution 只能得到一个稳定的布局输入，不因当前摘要布局、密度或显隐状态而改变。
2. 多指标图、分组图、Sankey、Treemap、宽屏单指标趋势图和富顶部摘要图均不存在持续切换。
3. 用户真实改变卡片大小、看板网格宽度或浏览器视口时，布局仍按现有产品阈值响应，并保留必要的布局和密度迟滞。
4. 摘要显隐不再依赖导致跨轴历史粘滞的 `previousShow`；固定布局与密度历史时，相同规范化尺寸的显隐结果不受此前显隐路径影响。
5. 不修改业务数据、图表字段映射、摘要统计口径、缓存加载流程或持久化看板配置。

## 根因

当前 `SQView` 同时观察卡片根容器和子级 `.chart-show-area`，并把 `.chart-show-area.clientWidth/clientHeight` 写入 `frameSize`。`resolveInsightDisplay()` 再使用该尺寸决定：

- 摘要使用顶部还是侧边布局；
- 根容器使用 `regular`、`compact`、`mini` 还是 `basic` 密度；
- 摘要是否显示以及最多展示多少统计项。

这些输出会改变根容器 padding、标题最小高度、标题下边距和部分工具栏间距，从而反过来改变被观察的 `.chart-show-area`。因此决策输入受决策输出影响：

```text
chart-show-area 尺寸
  -> resolveInsightDisplay
  -> 布局 / 密度 / 摘要显隐 class
  -> 外层 box model 改变
  -> chart-show-area 尺寸改变
  -> ResizeObserver 再次计算
```

现有迟滞只覆盖部分密度和宽屏趋势分支，无法给整个二维决策空间建立统一不变量。完整盒模型扫描已经在多指标/分组图、Sankey、单指标宽屏趋势图和富顶部摘要图的不同阈值附近发现不收敛点。继续给单个阈值增加迟滞会留下其他反馈路径，并使结果依赖历史状态。

约 7.5 秒后才开始抖动，是因为首屏使用无数据快照，缓存或数据库结果回填后摘要才挂载并启动反馈环；异步加载只是触发时机，不是根因。

## 方案选择

采用“规范化稳定帧”方案：布局策略使用由真实外部卡片尺寸推导、统一换算到 `compact` 基准盒模型的尺寸。内部摘要和图表区域的尺寸变化不再成为布局策略的独立触发源。

未采用以下方案：

- 为每个宽高阈值分别增加迟滞。该方案需要覆盖不断扩展的二维分支组合，仍会产生历史依赖和遗漏。
- 首次布局后锁定，直到下一次 resize。该方案会把异步数据到达前计算出的错误布局长期保留，只是隐藏反馈环。
- 固定所有密度的 padding 和标题高度。该方案虽然能削弱反馈，但会改变现有紧凑卡片的视觉密度，并不能约束未来新增的 density 相关样式。

## 设计

### 1. 统一测量所有权

`SQView` 的布局策略观察两个不受摘要内容支配的边界：`containerRef` 代表的卡片外部 border box，以及 `.dashboard-filter-controls` 工具栏包装层的 border box。挂载时完成一次初始测量；之后在根容器 border box 的宽高真实变化，或工具栏包装层因日期能力、pivot、组合换行或语言文本发生有效 block-size 变化时重新计算规范化尺寸。

根容器观察器显式使用 `border-box`，回调同时比较 border-box 宽高并去重，不能使用会随 padding 改变的默认 content box 判断“外部 resize”。工具栏包装层始终挂载，异步日期能力或 pivot 状态改变后由自身 border-box 观察事件触发；会改变包装层 margin 或组成、但不一定改变其 border box 的语义状态，同时通过 watcher 在 `nextTick` 后触发一次测量。`ResizeObserver` 不再观察 `.chart-show-area`，摘要挂载和图表重绘不会成为独立策略触发源。

图表渲染层仍根据自己实际获得的 DOM 空间执行 `autoFit` 或 resize。该行为只负责让图表填满已经分配的空间，不回写摘要布局策略。尺寸观察回调只更新规范化策略尺寸，不再从 `SQView` 额外调用 `scheduleRenderChart()`；实际 DOM resize 由 `ChartComponent` 的现有观察器统一负责，避免同一几何事件触发两套图表重建请求。数据、图表类型和字段配置变化所需的显式重绘路径保持不变。

图表身份、类型、轴配置等语义输入变化时，继续通过 `buildInsightLayoutStateKey()` 重置布局和密度历史；它们复用最近一次规范化外部尺寸，不通过观察子级尺寸生成新策略输入。

### 2. 规范化稳定帧

布局决策仍以图表可用区域的宽高为语义，但该宽高统一换算为“如果当前根容器使用 `compact` 外层盒模型时，图表区域会得到的尺寸”。规范化尺寸不再从当前 `.chart-show-area` 反推，而是直接由稳定外边界计算：

```text
规范化宽度
  = 根容器 border-box 宽度
  - 根容器边框
  - compact 基准水平 padding

规范化高度
  = 根容器 border-box 高度
  - 根容器边框
  - compact 基准垂直 padding
  - compact 基准标题高度与标题间距
  - 工具栏包装层的有效 block contribution
```

工具栏的有效 block contribution 是包装层 border-box 高度与其 block 方向外边距之和。工具栏不存在内容时为 `0`；日期、pivot、组合单行或组合换行都使用实际包装层贡献，不以单个子工具栏的固定值推测。

`compact` 基准值使用定义在 `SQView` 样式中的 CSS 自定义属性，并直接用于对应的实际 padding、标题高度和标题间距声明，避免 TypeScript 与 CSS 各自维护一套数字。当前基准为：

| 属性 | compact 基准值 |
| --- | ---: |
| 水平 padding | `16px` |
| 垂直 padding | `14px` |
| 标题最小高度 | `34px` |
| 标题下边距 | `10px` |

`.dashboard-filter-controls` 的外层 block contribution 必须在固定根宽度和固定工具栏结构下与 insight density 无关。为此，density 样式可以隐藏次要 pivot 文本或缩小内部 gap，但不得改变工具栏外层 margin、最小高度或行数；组合模式中的 pivot 区域使用与内容宽度无关的 flex basis 和 `min-width: 0`，避免隐藏内容改变换行决策。真正由根宽度、日期/pivot 组成或语言文本导致的换行仍是合法的结构尺寸变化，由工具栏观察器重新测量。

测量辅助函数负责读取和解析 CSS 基准值、根 border box、边框以及工具栏有效贡献，四舍五入后生成规范化 `width/height`。初始状态显式为 `unmeasured`：使用 `compact` 根样式但不挂载摘要，图表仍可按实际 DOM 空间初始化。首次得到正尺寸后进入正常策略；从隐藏页签或零尺寸恢复时，根 border-box 观察事件重新测量。缺少 CSS 属性、值不可解析或计算出非正尺寸时，不静默替换为其他字段或子级尺寸：保留上一份有效规范化尺寸；若从未成功测量则保持 `unmeasured`，并且同一错误只输出一次明确的开发诊断。

### 3. 布局状态与摘要显隐

`resolveInsightDisplay()` 继续是纯策略函数，并继续保留 `previousLayout` 与 `previousDensity`。这两类迟滞只在真实外部几何变化跨越阈值时发挥作用，避免用户拖拽卡片或浏览器 resize 在阈值附近产生视觉跳变。

删除 `previousShow` 对摘要重新进入的跨轴限制。摘要是否显示只由当前规范化宽高、图表类型和当前迟滞后的布局决定：小于可读下界时隐藏，恢复到可读范围时显示。这样在相同 `previousLayout/previousDensity` 下，`439x400 -> 520x400` 与直接进入 `520x400` 得到相同结果，不会因为此前由宽度触发过隐藏，就额外要求高度达到无关的 `430px`。

布局迟滞本身仍允许迟滞区间内的同一尺寸根据 `previousLayout` 保持 top 或 side，例如宽屏趋势图的 `1102x270`。这是用户真实 resize 的既有稳定策略，不属于 `previousShow` 路径依赖；测试分别固定布局历史验证显隐确定性，不把两种合法布局强行合并。

不改变以下现有产品策略：

- Sankey、Treemap、多 Y 指标和高分组数图表优先侧边摘要；
- 宽屏单指标时间趋势图在满足宽高比和尺寸条件时可使用侧边摘要；
- 富顶部摘要图按现有图表类型和宽度决定统计项密度；
- 极小卡片仍隐藏摘要，把空间留给图表。

### 4. 数据与渲染流程

修复后的流程为：

```text
根卡片挂载或外部尺寸真实变化
  OR 工具栏组成、换行或有效 block-size 变化
  -> 从稳定外边界生成 compact 基准规范化尺寸并去重
  -> resolveInsightDisplay
  -> 应用布局 / 密度 / 摘要显隐
  -> 图表渲染层适配实际剩余空间
  -> 内部尺寸变化不再回写布局策略
```

异步图表数据回填更新摘要内容和图表数据时，不会直接观察 `.chart-show-area`。若回填同时使日期工具栏或 pivot 工具栏出现，工具栏包装层的有效贡献变化会触发一次合法重测；若数据改变图表的布局资格，例如 Y 轴数量或 series 配置变化，状态 key 会重置策略历史，但仍使用最近的规范化稳定帧。

## 测试设计

实施必须先新增失败测试，再修改生产代码。

### 纯函数与盒模型闭环测试

新增可复用的盒模型模拟器，从根 border box、CSS compact 基准和工具栏有效贡献计算规范化输入。对阈值附近的宽高网格逐点扫描，要求在同一稳定外边界下：

- 规范化尺寸不随 `show/layout/density` 改变；
- 重复求值收敛，不出现两态或多态循环；
- 固定 `previousLayout/previousDensity` 时，相同规范化尺寸从不同 `previousShow` 历史进入的摘要显隐结果一致；
- 真实外部尺寸跨越迟滞边界时，布局与密度可以正常进入和退出。

扫描场景至少包括：

1. 四个及以上 Y 指标的 line、area、column、bar；
2. 六个及以上 series 分组的图表；
3. Sankey 与 Treemap；
4. 单指标、无 series 的宽屏日/周/月趋势图；
5. column、bar、heatmap、scatter、funnel 的富顶部摘要；
6. pie 普通顶部摘要；
7. table、metric 的无摘要生命周期；
8. 无数据、极小尺寸、恰好等于阈值以及阈值上下一个像素的边界。

### 组件结构契约测试

扩展 `SQView` 响应式测试，明确断言：

- `ResizeObserver` 只观察根容器和工具栏包装层，不观察 `.chart-show-area`；
- 根容器以 `border-box` 模式观察，density 只改变 padding 时不会被识别成外部尺寸变化；
- 规范化测量只在初始挂载、根容器 resize、工具栏有效贡献变化及对应语义 watcher 的 `nextTick` 中更新；
- 相同规范化尺寸不会重复调度图表重绘；
- 尺寸观察回调不调用 `scheduleRenderChart()`，实际 resize 只由 `ChartComponent` 负责；
- CSS 自定义属性直接驱动 compact padding、标题高度和间距，工具栏外层贡献不随 density 改变；
- `previousShow` 不再参与策略状态，语义 key 变化仍会正确重置布局和密度历史。

### 真实 DOM 盒模型测试

不能只让模拟器和生产函数共享同一组手写数字。必须在浏览器实际渲染的 `SQView` DOM 上固定根 border box，依次强制 `regular/compact/mini/basic`，读取根、工具栏和规范化尺寸，断言四种 density 的规范化结果一致。矩阵覆盖：无工具栏、仅日期、仅 pivot、日期与 pivot 组合单行、组合换行，以及中英文文本。该测试同时验证工具栏外层 block contribution 的 density 不变量；宽高允许最多 `1px` 的浏览器取整误差。

### 浏览器回归

在完整本地四服务环境中，登录后切换到 workspace `flam`，访问：

```text
http://127.0.0.1:5173/dashboard/index?resourceId=f26870db68cb44bd974b0160ea91cdae
```

使用真实看板和异步数据路径验证：

1. 视口固定为录屏复现尺寸 `1510x936`，目标为 `.canvas-container .wrapper-outer.is-report-chart-target .chart-base-container` 的第一个匹配项；
2. 等待目标内出现 `.chart-render-layer--active canvas` 或 `.chart-render-layer--active svg`，且 `.chart-loading-info` 不存在；
3. 此后每 `100ms` 采样一次，连续 `3s`，记录根 border box、density class、`.chart-show-area` 的 layout class、`.chart-insight-header` 是否存在和 `.chart-container` 宽度；
4. 根容器尺寸不变时，class 与摘要显隐必须完全一致，所有宽高波动不超过 `1px`；
5. 页面不出现重复加载遮罩或 ResizeObserver loop 警告；
6. 调整浏览器宽度和看板卡片尺寸跨越关键阈值，确认策略只随真实外部尺寸或工具栏有效贡献变化；
7. 至少抽查一个顶部摘要、一个侧边摘要和一个富顶部摘要图表，确认内容未被裁切或重叠。

最后运行相关 Node 聚焦测试、前端类型/构建检查以及仓库已有的图表响应式与渲染生命周期回归测试。

## 兼容性与非目标

- 不迁移或改写已保存的看板、图表、SQL、数据源和摘要配置。
- 不增加针对看板 ID、数据源名称、业务字段、指标含义或录屏数据的硬编码。
- 不通过隐藏全部摘要、延长 loading、限制异步加载或吞掉 ResizeObserver 错误来规避现象。
- 不在本次修改中重构通用图表库；图表渲染层的自身 resize 仅作为既有消费者保留。
- 本次“全局”指同一 `SQView` 布局策略覆盖的所有看板图表类型和看板入口，不改变 Smart Q&A 非看板表面的展示策略。
