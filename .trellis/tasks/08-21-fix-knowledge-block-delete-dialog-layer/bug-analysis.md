# Bug Analysis: 删除确认框被编辑抽屉遮挡

## Root Cause Category

- 类别：B - 跨组件库弹层契约不一致。
- `DocumentEditor.vue` 从 `element-plus` 导入 `ElMessageBox`，父级抽屉由项目默认的 `element-plus-secondary` 渲染。
- 两个组件库分别维护弹层 z-index，确认框进入 DOM 后仍位于 `.ed-drawer` 遮罩层后方，用户看到的是点击无响应。

## Why The Previous Fix Failed

- 上一次只在确认成功后增加 toast，没有验证确认框在真实抽屉中是否可见。
- 静态测试仅断言调用了 `ElMessageBox.confirm`，无法发现视觉层级错误。
- 运行时验证使用了错误服务，并没有走用户截图中的真实点击路径。

## Fix And Prevention

- 将 `ElMessageBox` 和 `ElMessage` 统一从 `element-plus-secondary` 导入。
- 回归测试禁止该编辑器重新从 `element-plus` 导入命令式弹层。
- 前端规范新增弹层组件库一致性约束，并要求抽屉内弹层做真实可见性验证。

## Verification

- 真实页面：新增未保存临时知识块，确认框可见并位于抽屉上方。
- 确认删除后数量从 17 恢复到 16，临时块消失，成功提示可见。
- 未点击保存草稿，现有业务知识未改变。
- 聚焦测试 20 项通过，定向 ESLint 通过，生产构建通过。
