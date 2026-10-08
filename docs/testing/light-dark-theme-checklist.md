# 深浅主题验收记录

日期：2026-09-28

工作树：`C:/Users/elex/.codex/worktrees/light-dark-theme/chat-bi`
分支：`codex/light-dark-theme`
基线：`712a28ea3ccd5bb132f0928c1c5bb51ddda1bafe`

## 已完成

- 同一主题开关控制首屏、页面状态、入口、品牌和图表；首次浅色，保存偏好，同源标签页同步，主题存储受限时本页仍可切换。
- 石墨灰语义颜色覆盖页面、工作区、导航、卡片、指标摘要、分析助手、组件库弹层、表格、图表和登录/门户页面。
- 保留 56px 顶栏、220px 展开侧栏、20px 看板外边距、16px 卡片间距和 8px 卡片圆角；摘要完整换行。
- 当前 SQPreview 使用已保存的绝对网格坐标，并没有自动双列容器。本次不重排用户自由布局或修改持久化配置；窄屏保留其现有画布滚动行为。自动双列转单列仅在验证夹具中展示，未把它伪装为产品现有能力。
- 原子渲染期间更新新图主题后再提交；旧实例销毁后不回写状态或向新图报告过期错误。
- G2 图例筛选与重选、分类 ID 配色、滑块和滚动条、连续图例区间均保持；S2 排序和滚动保持；切换无业务请求。
- 修复遍历矩形树图时发现的旧 G2 inline 数据连接器格式问题，附独立测试。

## 自动检查

- `npm exec vue-tsc -- -b --force`：通过。
- `npm run build`：通过。已有依赖注释和大 chunk 警告仍存在。
- 本次新增 15 项 Node 行为检查：通过，包含主题存储/开关、bootstrap、Less token、G2/S2 配色、异步调度、G2 状态缓存及矩形树图数据连接器。
- 相关 ChartComponent 原子绘制、尺寸、校验和 SQPreview 滚动边界回归：通过。
- 全量 `.test.mjs`：364 项，329 通过、35 失败。另用 Git 起点快照与相同依赖运行基线：349 项，314 通过、35 失败；失败名称集合一致，没有新增失败。

## 真实浏览器验证

浏览器使用独立 Playwright 会话与工作树 Vite 预览 `127.0.0.1:4173`；未操作原有 5173/8000/8001 服务或生产环境。

`frontend/tests/fixtures/theme-qa.html` 使用真实 ChartComponent、G2、S2、ThemeSwitcher 和日期控件，数据为合成夹具；周围导航是验证壳，不是已登录的业务页面截图。

在 frontend 运行：

```powershell
npx vite --host 127.0.0.1 --port 4173 --strictPort
npx --yes --package @playwright/cli playwright-cli -s=theme-qa open http://127.0.0.1:4173/tests/fixtures/theme-qa.html
npx --yes --package @playwright/cli playwright-cli -s=theme-qa run-code --filename tests/theme-browser-checks.cjs
npx --yes --package @playwright/cli playwright-cli -s=theme-qa run-code --filename tests/theme-browser-boundaries.cjs
```

第一组 20 项、第二组 7 项验证完成，覆盖：

- 全部 15 类图表真实渲染完成后切换主题。
- 已筛选图例保持筛选，隐藏色标保持禁用，重新选中恢复新主题色；空类别不会错配后续色标。
- S2 在同一实例中保持排序与滚动。
- 已打开日期面板同步为深色弹层。
- 连续快速切换、替换/卸载/重新挂载、多实例重复源 ID 不出现过期主题错误。
- 跨标签同步和刷新、非法偏好、系统深色与显式浅色冲突、主题存储读写拒绝。
- 1440/1280/1024/768px 双主题夹具截图；另记录 CSS zoom 125%/200% 截图（不是浏览器原生缩放断言）。
- 滑块区间、外层滚动条位置与连续图例选择范围保持。

没有宣称完成所有登录后业务路由、真实租户权限组合或嵌入宿主的端到端验收。富文本 iframe 适配保留编辑内容，当前依据类型检查与代码审查，未纳入浏览器夹具。

## 证据位置

本地截图保存在 `frontend/.playwright-cli/`，包括 `theme-dark-1440.png`、`theme-light-1440.png`、`theme-dark-calendar.png` 和其他宽度/缩放截图。
日志位于 `frontend/.superpowers/sdd/2026-09-28-light-dark-theme-switching/`：`build-final.log`、`tests-final.log`、`baseline-tests.log`、`browser-checks.log`、`browser-boundaries.log`。这些本机证据目录不提交。

## 基线失败清单

以下失败在实施前与实施后均存在：

- renders the analysis model selector before event metrics
- keeps property analysis isolated with property metrics, filters, and grouping
- keeps simultaneous and related-property controls while removing the red-box options
- reuses event metric aggregation behavior for simultaneous retention metrics
- adds rename and reused event-filter controls to both retention events
- provides ordered funnel steps with window and related-property controls
- keeps distribution analysis configuration and controls isolated from other models
- keeps distribution simultaneous event and aggregation on the same row
- keeps interval analysis isolated and exposes the reference controls
- keeps path analysis isolated and exposes event split and session controls
- keeps revenue analysis isolated with cohort, metric, cost, and observation controls
- keeps ranking analysis isolated with rank, tie, metric, and property controls
- keeps heatmap analysis isolated with event coordinates and map metadata
- src\views\dashboard\common\DashboardSqlEditor.builder-persistence.test.mjs
- src\views\dashboard\common\DashboardSqlEditor.event-filter-advice.test.mjs
- src\views\dashboard\common\DashboardSqlEditor.formula-event-metric.test.mjs
- 热力事件筛选入口与事件下拉保持在同一行
- 热力事件筛选树紧跟事件行且位于计算配置之前
- src\views\dashboard\common\DashboardSqlEditor.lazy-open.test.mjs
- src\views\dashboard\common\DashboardSqlEditor.preview-fields.test.mjs
- src\views\dashboard\common\DashboardSqlEditor.time-range-layout.test.mjs
- title-only apply updates the chart title without writing query state
- src\views\dashboard\components\sq-view\index.refresh-policy.test.mjs
- src\views\dashboard\components\sq-view\insightFrame.stability.test.mjs
- src\views\dashboard\editor\canvasRouteHandoff.test.mjs
- src\views\dashboard\editor\index.permission-refresh.test.mjs
- ordinary dashboard save can be dismissed outside
- platform template save can be dismissed outside
- resource rename save can be dismissed outside
- new dashboard save can be dismissed outside
- tree-order save can be dismissed outside after persistence completes
- normal message closure releases its listener without closing other messages
- src\views\dashboard\preview\SQPreviewShow.permission-refresh.test.mjs
- tests\chat-history-loading.test.mjs
- tests\datasource-timeout-default.test.mjs

## 侧栏文字可读性回归（2026-09-28）

- 修正资源树固定浅色选中底与深色文字组合的问题；局部组件与全局树样式改为使用同一组 `--theme-nav-active-*` 变量。
- 同步修正访问管理导航的选中状态与固定浅色表面；深色选中底 `#2C3D57`，文字和图标 `#79A6FF`。
- 新增 `frontend/tests/fixtures/resource-tree-theme.html`，加载实际 ResourceTree/Access SFC 样式与 Element Tree 控件；不依赖登录或业务数据。
- 浏览器脚本 `frontend/tests/resource-tree-theme-browser.cjs` 覆盖组件/全局样式两种加载顺序、浅深主题来回切换、树的两种选中模式、推荐/我的/嵌套/分组选中、悬停和键盘焦点，以及访问管理的选中和普通入口。
- 修复前复现截图中的浅字浅底，实测文字对比度约 1.05；修复后 42 种状态、168 个行样本全部通过，最小文字对比度 4.56、最小图标对比度 3.37。
- 本地验证截图：`frontend/.playwright-cli/sidebar-readable-dark.png`。


## 日期与 Card 边框参考图对齐（2026-09-28）

- 用户限定本次只调整日期与 Card 边框，指标排版、计算口径及图表数据保持原逻辑。
- 普通看板由外层 SQComponentWrapper 绘制一层 1px 主题边框，内部 SqView 不再重复描边；独立及 Tab/frameless 卡片保留自身边框。圆角统一为 8px，去除外层投影。
- 深色边框为 #394556，悬停为 #53647B；浅色边框继续使用浅灰蓝。
- DashboardDateExpressionPicker 增加通用 inline 外观：无底色日期标签、无按钮外框，显示“起始日期 至 结束日期”，快捷范围与箭头成组；默认编辑器 control 外观保留。
- 主卡片窄宽时日期区可换行；Tab 固定控制行保持单行，完整日期可从 title 与弹窗读取，避免遮挡摘要。
- 新增真实 SQComponentWrapper/SqView/日期选择器挂载夹具 tests/fixtures/dashboard-card-chrome.html，脚本 tests/dashboard-card-chrome-browser.cjs 验证 23 项：两套主题、边框归属、原日期入口、独立/Tab 卡片、260/300/340/680px、键盘打开/取消、只显示快捷范围、禁用态及窄宽静态自定义日期。
- 构建通过；全量 Node 测试保持 364 项 / 329 通过 / 35 项既有失败，无新增失败。
- 本地截图：frontend/.playwright-cli/reference-date-border-dark.png。

## 编辑画布边框补漏（2026-09-28）

- 原因：CanvasStyle.less 的 item-content 外壳保留固定白底、浅色 1px 边框、12px 圆角和阴影；内层 SqView 又绘制主题边框。此前预览验收未覆盖真实 CanvasShape 外壳。
- 编辑卡片外壳改用预览同一组主题变量，8px 圆角、无阴影；只移除外壳直接子图表的重复边框，Tab 内独立卡片不受影响。拖拽副本同步圆角；蓝色选中轮廓和八个控制点保留。
- 新增回归测试先复现固定浅色样式失败，修正后通过。相关 4 项 Node 测试、生产构建、独立代码审查通过。
- 真实 CanvasShape + SqView fixture 经深→浅→深验证：编辑与预览外壳颜色一致、1px 单层边框；内部图表边框 0px，Tab 图表仍为 1px；选中轮廓和 8 个控制点存在。
- 5173 的「新增看板」编辑态实测前三张卡片均为 `1px solid rgb(57,69,86)`、8px 圆角，内框 0px；未保存或修改业务数据。
- 本地截图：frontend/.playwright-cli/editor-card-border-dark.png。
