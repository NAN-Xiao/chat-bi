import assert from 'node:assert/strict'
import { existsSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'
import ts from 'typescript'

const currentDir = fileURLToPath(new URL('.', import.meta.url))
const sourcePath = join(currentDir, 'savedCanvasLayout.ts')
const canvasCorePath = join(currentDir, '../canvas/CanvasCore.vue')

assert.equal(existsSync(sourcePath), true, '应提供已保存看板布局校验工具')

const source = readFileSync(sourcePath, 'utf8')
const canvasCoreSource = readFileSync(canvasCorePath, 'utf8')
const initSource = canvasCoreSource.match(/function init\(\) \{[\s\S]*?\n\}/)?.[0] || ''

assert.match(initSource, /validateSavedCanvasLayout\(canvasComponentData\.value, itemMaxX\)/)
assert.match(initSource, /rebuildPositionBox\(\)/)
assert.doesNotMatch(initSource, /addItem\(/, '加载已有看板时不得逐项执行新增组件自动排版')
const compiled = ts.transpileModule(source, {
  compilerOptions: {
    module: ts.ModuleKind.ES2022,
    target: ts.ScriptTarget.ES2022,
  },
})
const tempDir = mkdtempSync(join(tmpdir(), 'saved-canvas-layout-'))
const compiledPath = join(tempDir, 'savedCanvasLayout.mjs')
writeFileSync(compiledPath, compiled.outputText, 'utf8')

try {
  const { validateSavedCanvasLayout } = await import(pathToFileURL(compiledPath).href)
  const items = [
    { id: 'first-in-array', x: 2, y: 37, sizeX: 70, sizeY: 15 },
    { id: 'second-in-array', x: 2, y: 18, sizeX: 70, sizeY: 18 },
  ]
  const before = structuredClone(items)

  assert.deepEqual(validateSavedCanvasLayout(items, 72), [])
  assert.deepEqual(items, before, '校验已保存布局时不得按数组顺序改写坐标')

  assert.deepEqual(
    validateSavedCanvasLayout(
      [
        { id: 'a', x: 1, y: 1, sizeX: 10, sizeY: 10 },
        { id: 'b', x: 5, y: 5, sizeX: 10, sizeY: 10 },
      ],
      72
    ),
    [{ type: 'overlap', itemIds: ['a', 'b'] }]
  )

  assert.deepEqual(
    validateSavedCanvasLayout([{ id: 'outside', x: 70, y: 0, sizeX: 4, sizeY: 2 }], 72),
    [{ type: 'invalid_frame', itemIds: ['outside'] }]
  )
} finally {
  rmSync(tempDir, { recursive: true, force: true })
}

console.log('Saved canvas layout tests passed')
