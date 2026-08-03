# 看板编辑页返回上下文修复设计

## 背景

普通看板详情页通过 `resourceId` 和 `dashboardMode` 共同确定当前看板及其所属区域。当前进入 `/canvas` 编辑页和从编辑页返回时只传递 `resourceId`，导致 `dashboardMode` 丢失，返回后无法稳定恢复当前编辑看板的分组、侧栏选中状态和详情上下文。

## 目标

- 从“我的看板”或“默认看板”进入编辑页时，显式保留当前 `dashboardMode`。
- 点击编辑页顶部返回按钮时，返回当前编辑看板，并恢复原看板模式。
- 缺失或非法的普通看板模式继续遵循现有规则，解析为 `my`。
- 平台模板编辑仍返回平台模板管理页，不改变现有行为。

## 方案

使用路由查询参数作为唯一来源，不依赖浏览器历史、Pinia 或会话存储：

1. 看板详情页和资源树的编辑入口构造 `/canvas` 路由时，同时传递 `resourceId` 与经现有工具规范化后的 `dashboardMode`。详情页头部使用预览组件加载后写入 `dashboardInfo` 的已解析模式，以兼容不在 URL 中携带模式的专用默认看板页。
2. 编辑页从当前路由读取并规范化 `dashboardMode`，通过 `baseParams` 传给工具栏。
3. 工具栏返回普通看板详情页时，构造 `/dashboard/index?resourceId=<当前看板>&dashboardMode=<原模式>`。
4. 新建看板保存后切换到资源编辑路由时，也保留规范化后的模式，确保随后返回行为一致。
5. 平台模板分支继续使用 `platformTemplateId` 和 `/system/dashboard-template`，不附加普通看板模式。

## 测试

- `my` 看板：编辑入口与返回目标均保留 `dashboardMode=my` 和当前 `resourceId`。
- `default` 看板：编辑入口与返回目标均保留 `dashboardMode=default` 和当前 `resourceId`。
- 缺失或非法模式：按现有普通看板规则解析为 `my`。
- 平台模板：返回模板管理页，行为不变。

## 非目标

- 不改为浏览器历史返回。
- 不新增持久化来源页状态。
- 不改变看板权限、数据源绑定或模板管理逻辑。
