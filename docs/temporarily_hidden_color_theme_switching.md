# 深浅主题切换维护说明

更新日期：2026-09-29。深浅主题已启用，并按登录账户保存。

## 当前状态

- `frontend/src/utils/themeConfig.ts` 中 `COLOR_THEME_SWITCHING_ENABLED = true`，`DEFAULT_THEME = 'light'`。
- `frontend/src/utils/theme.ts` 继续重新导出原有常量和类型，原调用方无需改导入路径。
- 复用顶栏现有 `ThemeSwitcher.vue`。账户偏好持久化于 `sys_user.color_theme`，通过 `GET/PUT /user/color-theme` 读取或更新；同一账户跨工作空间、浏览器及设备恢复选择。默认浅色，不跟随系统外观。
- Vite 的 `plugins/themeBootstrap.ts` 首屏使用默认浅色，身份校验后由 `accountTheme.ts` 加载服务器偏好；不读取旧的未区分账户的浏览器偏好，避免串号。短暂默认浅色到个人主题的切换是异步账户加载的正常过程。
- `theme.ts` 只负责应用视觉状态。`shuzhi-theme-mode:<用户ID>` 仅发送已保存设置的失效通知，接收方重新查询服务器，不信任事件携带的旧值，也不作为服务器读取失败的兜底。存储受限不影响服务器保存。
- 保存时立即预览并禁用重复点击；失败恢复已确认配色并提示。同账号并发标签页写入会重新读取服务器结果。退出或切换账号时清除运行期绑定，旧请求不能改变新会话配色。
- 账户校验头 `X-SHUZHI-ACCOUNT-ID` 只用于断言请求所属账号，不能指定更新其他用户；嵌入式身份不读取或修改助手所有者的账户偏好。
- `frontend/src/styles/theme-tokens.less` 是页面和图表配色源。`--theme-*`、`--workspace-*`、两套组件库变量继续供现有组件使用。
- G2 通过交互状态 reducer 更新视觉，S2 在原实例更新主题，DOM 指标和摘要色点读取 CSS 变量。切换不查询业务数据。

## 回退为强制浅色

将 `themeConfig.ts` 中开关改为 `false` 后重新构建即可。初始化、运行期 API、按钮和 logo 都必须遵守开关，旧 dark 缓存不能绕过它；暂停读取/写入账户配色但不删除账户已保存设置。保留组件、存储键、事件名、样式和图表适配器。

不要增加第二个开关、URL 调试后门或系统自动跟随。历史说明中“applyTheme 会无条件写回 light 缓存”的行为已经移除：初始化不再无意义地重写偏好。

## 图表升级注意事项

`g2ThemeGuides.ts` 显式适配当前 G2 5 交互状态缓存 `__ordinal__` / `__states__`，防止重新选中图例时恢复旧主题。升级 G2 或其 GUI 依赖时，必须运行真实浏览器的图例筛选、重选、滑块、滚动条及连续图例测试。

分类色按当前 scale 的类别 ID 取值，不按“可见图例行号”重新分配。DOM 摘要和 canvas 共用 `--theme-chart-series-*`。

## 验证

详见 `docs/testing/light-dark-theme-checklist.md`。验证前端命令均在任务工作树的 `frontend` 目录执行。

账户偏好新增迁移 `171_account_color_theme.py`，部署顺序为数据库迁移、后端、前端。迁移只新增带默认值和 light/dark 约束的字段；不要把旧的浏览器全局值批量归属给任何账户。

账户专项回归：`frontend/tests/accountTheme.test.mjs`、`theme.test.mjs`、`themeBootstrap.test.mjs`；后端 `backend/tests/test_account_color_theme.py` 验证持久化、跨空间一致、账户隔离、参数校验和嵌入拒绝。
