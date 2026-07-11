import assert from 'node:assert/strict'
import { existsSync, readFileSync, writeFileSync, mkdtempSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'
import ts from 'typescript'

const currentDir = fileURLToPath(new URL('.', import.meta.url))
const sourcePath = join(currentDir, 'dashboardOptions.ts')

assert.equal(existsSync(sourcePath), true, '应提供可复用的看板选项扁平化工具')

const source = readFileSync(sourcePath, 'utf8')
const compiled = ts.transpileModule(source, {
  compilerOptions: {
    module: ts.ModuleKind.ES2022,
    target: ts.ScriptTarget.ES2022,
  },
})

const tempDir = mkdtempSync(join(tmpdir(), 'dashboard-options-'))
const compiledPath = join(tempDir, 'dashboardOptions.mjs')
writeFileSync(compiledPath, compiled.outputText, 'utf8')

try {
  const { flattenSelectableDashboardOptions } = await import(pathToFileURL(compiledPath).href)

  const options = flattenSelectableDashboardOptions([
    {
      id: 'folder-a',
      name: '测试',
      node_type: 'folder',
      leaf: false,
      children: [
        {
          id: 'leaf-a',
          name: 'SQL生成测试',
          node_type: 'leaf',
          leaf: true,
          can_edit: true,
          is_default: false,
          children: [],
        },
      ],
    },
    {
      id: 'leaf-b',
      name: '444',
      node_type: 'leaf',
      leaf: true,
      can_edit: true,
      is_default: false,
      children: [],
    },
    {
      id: 'readonly-leaf',
      name: '只读看板',
      node_type: 'leaf',
      leaf: true,
      can_edit: false,
      is_default: false,
      children: [],
    },
  ])

  assert.deepEqual(
    options,
    [
      { id: 'leaf-a', name: 'SQL生成测试', level: 1 },
      { id: 'leaf-b', name: '444', level: 0 },
    ],
    '添加到我的看板时应递归展开子节点，只返回可编辑的叶子看板，并保留层级缩进信息'
  )
} finally {
  rmSync(tempDir, { recursive: true, force: true })
}
