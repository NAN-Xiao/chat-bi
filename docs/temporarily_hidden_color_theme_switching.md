# 颜色主题切换入口临时隐藏备忘

记录日期：2026-06-25

## 背景

深色主题仍有较多视觉细节未修完。为了避免用户切换后遇到不完整体验，颜色主题切换入口暂时全部隐藏，应用默认保持浅色主题。

这次处理是临时屏蔽，不是删除深色主题能力。

## 当前实现

前端主题工具位置：

```text
frontend/src/utils/theme.ts
```

当前通过固定开关关闭入口和深色应用：

```ts
export const COLOR_THEME_SWITCHING_ENABLED = false
export const DEFAULT_THEME: ThemeMode = 'light'
```

当 `COLOR_THEME_SWITCHING_ENABLED` 为 `false` 时：

- `getInitialTheme()` 固定返回浅色，忽略旧的本地深色缓存。
- `applyTheme(...)` 会把任何传入主题折回浅色，并写回本地缓存。
- `getNextTheme(...)` 固定返回浅色。
- `ThemeSwitcher.vue` 不渲染按钮入口。

## 必须保留的内容

以下内容暂时不要删除，除非后续明确决定彻底下线深色主题：

- `frontend/src/components/layout/ThemeSwitcher.vue`
- `frontend/src/utils/theme.ts` 中的主题工具函数、事件名和存储 key
- `frontend/src/style.less` 以及相关页面中的 `:root[data-theme='dark']` 兼容样式
- 依赖 `THEME_CHANGE_EVENT` 或 `getInitialTheme()` 做品牌/logo 适配的逻辑

## 恢复方式

如果后续深色主题修完，需要重新显示颜色主题切换入口，先完成视觉回归后把：

```ts
export const COLOR_THEME_SWITCHING_ENABLED = false
```

改为：

```ts
export const COLOR_THEME_SWITCHING_ENABLED = true
```

然后运行前端类型检查：

```bash
npm exec vue-tsc -- -b --force
```

## 注意事项

- 不要新增其他主题切换入口、系统深色自动跟随或绕过 `COLOR_THEME_SWITCHING_ENABLED` 的调用。
- 不要把这次临时隐藏误判为废弃代码清理。
- 恢复前需要覆盖主布局、系统管理、智能问答、看板预览、弹窗、表格、图表、登录页等关键界面。
