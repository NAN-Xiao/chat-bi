# 侧栏子菜单箭头位置修复实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将纵向侧栏子菜单的展开/收起箭头固定在菜单项右侧，距右边缘 `8px`，同时保留垂直居中和旋转行为。

**Architecture:** 保留 `element-plus-secondary` 生成的子菜单 DOM，在现有纵向菜单样式作用域内显式建立标题与箭头的相对/绝对定位关系，并覆盖组件库宽度和通用图标外边距。使用源码样式回归测试锁定纵向规则，避免影响横向顶栏菜单。

**Tech Stack:** Vue 3、Less、element-plus-secondary、Node.js 内置测试运行器

## Global Constraints

- 纵向侧栏箭头容器宽度固定为 `12px`。
- 箭头距菜单项右边缘保持 `8px`，并继续垂直居中。
- 标题作为定位参照，箭头使用绝对定位且不继承通用图标右外边距。
- 展开和收起状态的旋转动画保持不变。
- 横向顶栏菜单样式不受影响。
- 不调整菜单项文字、图标、行高或侧栏宽度。

---

### Task 1: 固定纵向子菜单箭头位置

**Files:**
- Create: `frontend/src/components/layout/Menu.layout.test.mjs`
- Modify: `frontend/src/components/layout/Menu.vue:367`
- Test: `frontend/src/components/layout/Menu.layout.test.mjs`

**Interfaces:**
- Consumes: `Menu.vue` 中 `.ed-menu-vertical .ed-sub-menu__icon-arrow` 的现有绝对定位规则。
- Produces: 仅作用于纵向菜单的 `width: 12px !important` 样式约束；不新增 JavaScript 或组件接口。

- [ ] **Step 1: 编写失败的样式回归测试**

创建 `frontend/src/components/layout/Menu.layout.test.mjs`：

```javascript
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'

const source = readFileSync(fileURLToPath(new URL('./Menu.vue', import.meta.url)), 'utf8')
const verticalMenuStart = source.indexOf('.ed-menu-vertical {')
const horizontalMenuStart = source.indexOf('.shuzhi-layout-menu-horizontal {')

assert.ok(verticalMenuStart >= 0, '应存在纵向菜单样式作用域')
assert.ok(horizontalMenuStart > verticalMenuStart, '横向菜单样式应位于纵向菜单样式之后')

const verticalMenuStyles = source.slice(verticalMenuStart, horizontalMenuStart)

assert.match(
  verticalMenuStyles,
  /\.ed-sub-menu \.ed-sub-menu__title\s*\{[\s\S]*?position:\s*relative\s*!important;/,
  '纵向侧栏子菜单标题应作为箭头的定位参照'
)

assert.match(
  verticalMenuStyles,
  /\.ed-sub-menu__icon-arrow\s*\{[\s\S]*?position:\s*absolute\s*!important;[\s\S]*?width:\s*12px\s*!important;[\s\S]*?right:\s*8px\s*!important;[\s\S]*?margin-right:\s*0\s*!important;[\s\S]*?margin-top:\s*-8px\s*!important;/,
  '纵向侧栏子菜单箭头应使用固定宽度和绝对定位，并精确停靠在菜单项右侧和垂直中心'
)
```

- [ ] **Step 2: 运行测试并确认预期失败**

Run: `cd frontend; node --test src/components/layout/Menu.layout.test.mjs`

Expected: FAIL，错误信息包含“纵向侧栏子菜单标题应作为箭头的定位参照”，原因是纵向标题和箭头尚未建立明确的定位关系。

- [ ] **Step 3: 实施最小样式修改**

在 `frontend/src/components/layout/Menu.vue` 的 `.ed-menu-vertical` 内，将箭头规则修改为：

```less
  .ed-sub-menu__icon-arrow {
    position: absolute !important;
    width: 12px !important;
    top: 50% !important;
    right: 8px !important;
    margin-right: 0 !important;
    margin-top: -8px !important;
  }
```

同时在 `.ed-sub-menu .ed-sub-menu__title` 中加入：

```less
    position: relative !important;
```

不要修改 `.shuzhi-layout-menu-horizontal .ed-sub-menu .ed-sub-menu__icon-arrow`，也不要覆盖箭头的 `transform`。

- [ ] **Step 4: 运行聚焦测试并确认通过**

Run: `cd frontend; node --test src/components/layout/Menu.layout.test.mjs`

Expected: PASS，`1` 个测试文件通过且无错误。

- [ ] **Step 5: 运行前端构建检查**

Run: `cd frontend; npm run build`

Expected: `vue-tsc -b` 和 `vite build` 均以退出码 `0` 完成。

- [ ] **Step 6: 进行页面视觉验证**

打开工作空间管理的数据字典页面，在桌面视口检查左侧“系统设置”菜单：

```text
收起状态：箭头距菜单项右边缘约 8px，且垂直居中。
展开状态：箭头位置不移动，只按现有规则旋转；子菜单正常显示。
横向顶栏：下拉箭头样式和位置保持原样。
```

同时读取箭头元素计算样式和几何位置，确认 `width` 为 `12px`、`right` 为 `8px`、标题右缘到箭头右缘为 `8px`，且两者垂直中心误差为 `0px`。

- [ ] **Step 7: 提交实现**

```powershell
git add -- frontend/src/components/layout/Menu.layout.test.mjs frontend/src/components/layout/Menu.vue
git commit -m "修复侧栏子菜单箭头位置"
```
