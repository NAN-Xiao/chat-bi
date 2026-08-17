import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'

import {
  downloadKnowledgeMarkdownTemplate,
  knowledgeMarkdownTemplates,
} from '../src/views/knowledge-base/knowledgeMarkdownTemplates.ts'
import {
  KnowledgeMarkdownFormatError,
  parseKnowledgeMarkdownTemplate,
} from '../src/views/knowledge-base/knowledgeMarkdownFormat.ts'

test('提供四类标题切片友好的 Markdown 模板', () => {
  assert.deepEqual(
    knowledgeMarkdownTemplates.map(({ id, label, fileName }) => ({ id, label, fileName })),
    [
      { id: 'document', label: '普通文档', fileName: '知识库-普通文档模板.md' },
      { id: 'business-sql', label: '业务术语与 SQL', fileName: '知识库-业务术语与SQL模板.md' },
      { id: 'event-parameters', label: '事件参数', fileName: '知识库-事件参数模板.md' },
      {
        id: 'table-fields-json-path',
        label: '表字段与 JSON Path',
        fileName: '知识库-表字段与JSON-Path模板.md',
      },
    ]
  )

  for (const template of knowledgeMarkdownTemplates) {
    const parsed = parseKnowledgeMarkdownTemplate(template.content)
    assert.equal(parsed.templateType, 'knowledge_document')
    assert.equal(parsed.templateVersion, 1)
    assert.doesNotMatch(parsed.markdown, /template_type|template_version/)
    assert.match(template.content, /^---\ntemplate_type: knowledge_document\ntemplate_version: 1\n---\n/)
    assert.match(template.content, /^#\s+\S/m)
    assert.match(template.content, /^##\s+\S/m)
    assert.match(template.content, /填写提示/)
    assert.match(template.content, /请替换/)
    assert.equal(template.fileName.endsWith('.md'), true)
    assert.equal(template.content.length < 12 * 1024, true)
    assert.doesNotMatch(template.content, /datasource[_ -]?id\s*[:=]\s*\d+/i)
    assert.doesNotMatch(template.content, /(password|api[_ -]?key|secret)\s*[:=]\s*\S+/i)
  }

  const businessTemplate = knowledgeMarkdownTemplates.find(({ id }) => id === 'business-sql')
  assert.ok(businessTemplate)
  assert.match(businessTemplate.content, /```sql[\s\S]+```/)
})

test('严格拒绝缺少模板标记、未知版本和不完整 Markdown', () => {
  for (const source of [
    '# 标题\n\n## 章节\n正文',
    '---\ntemplate_type: bad\ntemplate_type: knowledge_document\ntemplate_version: 1\n---\n# 标题\n## 章节\n正文',
    '---\ntemplate_type: knowledge_document\ntemplate_version: 2\n---\n# 标题\n## 章节\n正文',
    '---\ntemplate_type: knowledge_document\ntemplate_version: 1\n---\n## 缺少一级标题\n正文',
    '---\ntemplate_type: knowledge_document\ntemplate_version: 1\n---\n# 标题\n正文',
    '---\ntemplate_type: knowledge_document\ntemplate_version: 1\n---\n# 标题\n## 章节\n```sql\nselect 1',
  ]) {
    assert.throws(
      () => parseKnowledgeMarkdownTemplate(source),
      (error) => error instanceof KnowledgeMarkdownFormatError && error.message.startsWith('格式错误')
    )
  }
})

test('下载函数使用所选模板的 UTF-8 Markdown 内容和文件名', async () => {
  const template = knowledgeMarkdownTemplates[2]
  let downloadedBlob: Blob | null = null
  let clicked = 0
  let appended = 0
  let removed = 0
  let revoked = ''
  const events: string[] = []
  const scheduledCallbacks: Array<() => void> = []
  const anchor = {
    href: '',
    download: '',
    hidden: false,
    click: () => {
      clicked += 1
      events.push('click')
    },
    remove: () => {
      removed += 1
      events.push('remove')
    },
  }
  const originalDocument = Object.getOwnPropertyDescriptor(globalThis, 'document')
  const originalCreateObjectURL = URL.createObjectURL
  const originalRevokeObjectURL = URL.revokeObjectURL
  const originalSetTimeout = globalThis.setTimeout

  Object.defineProperty(globalThis, 'document', {
    configurable: true,
    value: {
      createElement: () => anchor,
      body: {
        appendChild: () => {
          appended += 1
        },
      },
    },
  })
  URL.createObjectURL = (blob: Blob) => {
    downloadedBlob = blob
    return 'blob:knowledge-template'
  }
  URL.revokeObjectURL = (url: string) => {
    revoked = url
    events.push('revoke')
  }
  globalThis.setTimeout = ((callback: TimerHandler, delay?: number) => {
    assert.equal(delay, 0)
    assert.equal(typeof callback, 'function')
    events.push('schedule')
    scheduledCallbacks.push(callback as () => void)
    return 1
  }) as typeof setTimeout

  try {
    downloadKnowledgeMarkdownTemplate(template)
    assert.equal(revoked, '')
    assert.deepEqual(events, ['click', 'remove', 'schedule'])
    assert.equal(scheduledCallbacks.length, 1)
    const releaseObjectUrl = scheduledCallbacks[0]
    assert.ok(releaseObjectUrl)
    releaseObjectUrl()

    assert.ok(downloadedBlob)
    assert.equal(downloadedBlob.type, 'text/markdown;charset=utf-8')
    assert.equal(await downloadedBlob.text(), template.content)
    assert.equal(anchor.download, template.fileName)
    assert.equal(anchor.href, 'blob:knowledge-template')
    assert.equal(anchor.hidden, true)
    assert.equal(clicked, 1)
    assert.equal(appended, 1)
    assert.equal(removed, 1)
    assert.equal(revoked, 'blob:knowledge-template')
    assert.deepEqual(events, ['click', 'remove', 'schedule', 'revoke'])
  } finally {
    if (originalDocument) Object.defineProperty(globalThis, 'document', originalDocument)
    else Reflect.deleteProperty(globalThis, 'document')
    URL.createObjectURL = originalCreateObjectURL
    URL.revokeObjectURL = originalRevokeObjectURL
    globalThis.setTimeout = originalSetTimeout
  }
})

test('知识库管理页通过分组工具栏接入模板下拉入口', async () => {
  const source = await readFile(
    new URL('../src/views/knowledge-base/KnowledgeBaseV2Panel.vue', import.meta.url),
    'utf8'
  )

  assert.match(source, /<el-dropdown[^>]+@command="downloadMarkdownTemplate"/)
  assert.match(source, /v-for="template in knowledgeMarkdownTemplates"/)
  assert.match(source, /:command="template\.id"/)
  assert.match(source, /function downloadMarkdownTemplate\(command: string \| number \| object\)/)
  assert.doesNotMatch(source, /:command="template"/)
  assert.match(source, /下载 Markdown 模板/)
  const panelActionsRule = source.match(/\.panel-actions\s*\{([^}]+)\}/)?.[1] || ''
  assert.match(panelActionsRule, /width:\s*100%/)
  assert.match(panelActionsRule, /min-width:\s*0/)
  assert.match(panelActionsRule, /justify-content:\s*flex-end/)
  assert.match(panelActionsRule, /flex-wrap:\s*wrap/)
  assert.match(source, /<div class="panel-filters">[\s\S]*class="knowledge-filter-input"[\s\S]*搜索知识库[\s\S]*class="knowledge-filter-scope"[\s\S]*平台知识库[\s\S]*工作空间知识库[\s\S]*class="knowledge-filter-workspace"[\s\S]*选择工作空间[\s\S]*<\/div>/)
  assert.match(source, /const workspaceFilterDisabled = computed\(\(\) => !isPlatformAdmin\.value\)/)
  assert.match(source, /:disabled="workspaceFilterDisabled"/)
  assert.match(source, /<div class="panel-buttons">[\s\S]*刷新[\s\S]*检索预览[\s\S]*下载 Markdown 模板[\s\S]*新建知识库[\s\S]*<\/div>/)
  assert.match(source, /\.knowledge-filter-input \{ width: 220px; flex: 0 0 220px; \}/)
  assert.match(source, /\.knowledge-filter-scope \{ width: 150px; flex: 0 0 150px; \}/)
  assert.match(
    source,
    /@media \(max-width: 1440px\)[^{]*\{[^}]*\.panel-actions \{ justify-content: space-between; \}/s
  )
  assert.match(
    source,
    /@media \(max-width: 680px\)[\s\S]*\.knowledge-filter-input, \.knowledge-filter-scope, \.knowledge-filter-workspace, \.knowledge-archive-filter \{ width: 100%; flex-basis: auto; \}/
  )
  assert.match(source, /\.panel-buttons \{ display: grid; grid-template-columns: repeat\(2, minmax\(0, 1fr\)\); align-items: stretch; \}/)
  assert.match(
    source,
    /\.template-download :deep\(\.ed-button\) \{ width: 100%; height: auto; min-height: 32px; white-space: normal; \}/
  )
})

test('知识库管理使用双下拉并向普通成员开放只读入口', async () => {
  const [v2Source, legacySource, routerSource, scopeNavigationSource] = await Promise.all([
    readFile(new URL('../src/views/knowledge-base/KnowledgeBaseV2Panel.vue', import.meta.url), 'utf8'),
    readFile(new URL('../src/views/knowledge-base/index.vue', import.meta.url), 'utf8'),
    readFile(new URL('../src/router/index.ts', import.meta.url), 'utf8'),
    readFile(new URL('../src/views/knowledge-base/knowledgeScopeNavigation.ts', import.meta.url), 'utf8'),
  ])

  for (const source of [v2Source, legacySource]) {
    assert.match(source, /平台知识库/)
    assert.match(source, /工作空间知识库/)
    assert.match(source, /workspaceFilterDisabled/)
    assert.match(source, /userStore\.isTenantAdminUser/)
  }
  assert.match(v2Source, /row\.archived \|\| !row\.can_manage \? '查看' : '编辑'/)
  assert.match(legacySource, /row\.can_manage \? '可管理' : '只读'/)
  const routeStart = routerSource.indexOf("path: 'knowledge-base'")
  const routeEnd = routeStart >= 0 ? routerSource.indexOf("path: 'prompt'", routeStart) : -1
  const knowledgeRoute = routeStart >= 0 && routeEnd > routeStart
    ? routerSource.slice(routeStart, routeEnd)
    : ''
  assert.match(knowledgeRoute, /tenantBusiness:\s*true/)
  assert.match(knowledgeRoute, /platformOperation:\s*true/)
  assert.doesNotMatch(knowledgeRoute, /tenantAdminOnly:\s*true/)
  assert.match(knowledgeRoute, /path:\s*'platform'/)
  assert.match(knowledgeRoute, /path:\s*'workspace'/)
  assert.match(scopeNavigationSource, /system-platform-knowledge-base/)
  assert.match(scopeNavigationSource, /system-workspace-knowledge-base/)
})
