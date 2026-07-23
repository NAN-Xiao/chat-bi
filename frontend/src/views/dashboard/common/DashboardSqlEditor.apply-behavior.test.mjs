import assert from 'node:assert/strict'
import esbuild from 'esbuild'
import { readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const currentDir = dirname(fileURLToPath(import.meta.url))
const componentPath = join(currentDir, 'DashboardSqlEditor.vue')
const source = readFileSync(componentPath, 'utf8')
const coordinatorPath = join(currentDir, 'dashboardSqlApplyCoordinator.ts')
const coordinatorBuild = await esbuild.build({
  entryPoints: [coordinatorPath],
  bundle: true,
  format: 'esm',
  platform: 'node',
  write: false,
})
const coordinatorModule = await import(
  `data:text/javascript;base64,${Buffer.from(coordinatorBuild.outputFiles[0].text).toString('base64')}`
)
const { runDashboardSqlApply } = coordinatorModule

function functionSource(name, nextName) {
  const match = source.match(
    new RegExp(`(?:async )?function ${name}\\([\\s\\S]*?\\r?\\n\\}(?=\\r?\\n\\r?\\n(?:async )?function ${nextName}\\()`)
  )
  assert.ok(match, `需要保留 ${name} 函数`)
  return match[0]
}

const applyChangeSource = functionSource('applyChange', 'closeDrawer')
const closeDrawerSource = source.match(/function closeDrawer\(\) \{[\s\S]*?\r?\n\}/)?.[0]
assert.ok(closeDrawerSource, '需要保留 closeDrawer 函数')

function createRuntime(executor) {
  const props = {
    viewInfo: { id: 'chart-1' },
    applyExecutor: executor,
  }
  const applying = { value: false }
  const visible = { value: true }
  const calls = {
    applied: 0,
    execute: 0,
    success: 0,
    write: 0,
  }
  const wrappedExecutor = executor
    ? async (viewInfo) => {
        calls.execute += 1
        return executor(viewInfo)
      }
    : undefined
  props.applyExecutor = wrappedExecutor
  const applyChange = new Function(
    'props',
    'applying',
    'validateBeforeApply',
    'writeEditorStateToViewInfo',
    'emits',
    'visible',
    'ElMessage',
    't',
    'runDashboardSqlApply',
    `${applyChangeSource}; return applyChange`
  )(
    props,
    applying,
    () => true,
    () => {
      calls.write += 1
      return true
    },
    (event) => {
      if (event === 'applied') calls.applied += 1
    },
    visible,
    { success: () => { calls.success += 1 } },
    (key) => key,
    runDashboardSqlApply
  )
  const closeDrawer = new Function(
    'applying',
    'visible',
    `${closeDrawerSource}; return closeDrawer`
  )(applying, visible)
  return { applyChange, applying, calls, closeDrawer, visible }
}

{
  const runtime = createRuntime(undefined)
  const applyPromise = runtime.applyChange()
  assert.equal(runtime.calls.applied, 1, '未配置执行器时应保持原有同步 applied 行为')
  assert.equal(runtime.visible.value, false, '未配置执行器时应保持原有同步关闭行为')
  assert.equal(runtime.applying.value, false, '未配置执行器时不应留下异步 loading')
  await applyPromise
}

{
  const runtime = createRuntime(async () => true)
  await runtime.applyChange()
  assert.equal(runtime.calls.execute, 1, '成功时应执行一次异步保存')
  assert.equal(runtime.calls.applied, 1, '成功时应发出 applied')
  assert.equal(runtime.visible.value, false, '成功时应关闭抽屉')
  assert.equal(runtime.applying.value, false, '成功后应恢复 applying')
}

{
  const runtime = createRuntime(async () => false)
  await runtime.applyChange()
  assert.equal(runtime.calls.applied, 0, '保存返回 false 时不得发出 applied')
  assert.equal(runtime.visible.value, true, '保存返回 false 时必须保持抽屉打开')
  assert.equal(runtime.applying.value, false, '保存返回 false 后应恢复 applying')
}

{
  const runtime = createRuntime(async () => {
    throw new Error('save failed')
  })
  await assert.rejects(runtime.applyChange(), /save failed/)
  assert.equal(runtime.calls.applied, 0, '保存抛错时不得发出 applied')
  assert.equal(runtime.visible.value, true, '保存抛错时必须保持抽屉打开')
  assert.equal(runtime.applying.value, false, '保存抛错后应恢复 applying')
}

{
  let resolveSave
  const saveResult = new Promise((resolve) => {
    resolveSave = resolve
  })
  const runtime = createRuntime(() => saveResult)
  const firstApply = runtime.applyChange()
  const secondApply = runtime.applyChange()
  assert.equal(runtime.calls.execute, 1, '重复点击只能执行一次异步保存')
  resolveSave(true)
  await Promise.all([firstApply, secondApply])
  assert.equal(runtime.calls.applied, 1, '重复点击最终只能发出一次 applied')
  assert.equal(runtime.applying.value, false, '重复点击完成后应恢复 applying')
}

{
  let resolveSave
  const saveResult = new Promise((resolve) => {
    resolveSave = resolve
  })
  const runtime = createRuntime(() => saveResult)
  const applyingPromise = runtime.applyChange()
  assert.equal(runtime.applying.value, true, '异步保存期间 applying 应为 true')
  runtime.closeDrawer()
  try {
    assert.equal(runtime.visible.value, true, '异步保存期间 closeDrawer 必须拒绝关闭请求')
  } finally {
    resolveSave(false)
    await applyingPromise
  }
  assert.equal(runtime.applying.value, false, '关闭请求被拒绝后 finally 仍应恢复 applying')
}

assert.match(source, /:before-close="handleBeforeClose"/, '抽屉关闭前必须统一经过门禁')
assert.match(source, /:close-on-click-modal="!applying"/, '保存期间必须禁用遮罩关闭')
assert.match(source, /:close-on-press-escape="!applying"/, '保存期间必须禁用 Esc 关闭')
assert.match(source, /:show-close="!applying"/, '保存期间必须隐藏抽屉 X')
assert.match(source, /<el-button secondary :disabled="applying" @click="closeDrawer">/, '保存期间必须禁用取消按钮')

console.log('DashboardSqlEditor apply behavior passed')
