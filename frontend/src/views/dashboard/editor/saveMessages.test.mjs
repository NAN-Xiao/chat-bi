import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'
import vm from 'node:vm'
import ts from 'typescript'

const dismissibleHelperSource = readFileSync(
  new URL('../../../utils/dismissibleMessage.ts', import.meta.url),
  'utf8'
)

test('dismissible messages use the application message component library', () => {
  assert.match(
    dismissibleHelperSource,
    /import \{ ElMessage \} from 'element-plus-secondary'/
  )
})

// Execute the production handlers. Only persistence and the message renderer
// are replaced; the outside-click lifecycle is the real shared implementation.
function loadHandler(relativePath, name, context) {
  const source = readFileSync(new URL(relativePath, import.meta.url), 'utf8')
  const script = source.includes('<script')
    ? source.match(/<script[^>]*>([\s\S]*?)<\/script>/)[1]
    : source
  const ast = ts.createSourceFile(relativePath, script, ts.ScriptTarget.Latest, true)
  for (const statement of ast.statements) {
    if (ts.isVariableStatement(statement)) {
      const declaration = statement.declarationList.declarations.find(
        (item) => item.name.getText(ast) === name
      )
      if (declaration) {
        const code = ts.transpile(`const ${declaration.getText(ast)}`, {
          target: ts.ScriptTarget.ES2022,
        })
        return vm.runInContext(`${code}; ${name}`, context)
      }
    }
  }
  throw new Error(`Handler not found: ${name}`)
}

function setup() {
  const listeners = new Set()
  const messages = new Set()
  class Element {
    constructor(customClass) {
      this.classList = { contains: (name) => name === customClass }
    }
  }
  const render = (options) => {
    const record = {
      message: options.message,
      element: new Element(options.customClass),
      close() {
        messages.delete(record)
        options.onClose?.()
      },
    }
    messages.add(record)
    return record
  }
  const ElMessage = (options) => render(options)
  ElMessage.success = (options) =>
    render(typeof options === 'string' ? { message: options } : options)
  const document = {
    addEventListener(type, handler, capture) {
      assert.equal(type, 'click')
      assert.equal(capture, true, 'outside dismissal must work with propagation-stopping controls')
      listeners.add(handler)
    },
    removeEventListener(type, handler, capture) {
      assert.equal(type, 'click')
      assert.equal(capture, true)
      listeners.delete(handler)
    },
  }
  const context = vm.createContext({ Element, document, ElMessage, t: (key) => key })
  const helper = readFileSync(
    new URL('../../../utils/dismissibleMessage.ts', import.meta.url),
    'utf8'
  )
    .replace(/^import .*\n/m, '')
    .replace('export function', 'function')
  vm.runInContext(ts.transpile(helper, { target: ts.ScriptTarget.ES2022 }), context)
  const click = (path = []) => {
    for (const handler of [...listeners]) handler({ composedPath: () => path })
  }
  return { context, messages, listeners, click }
}

function assertDismissible(harness) {
  assert.equal(harness.messages.size, 1, 'successful save must show one message')
  const [message] = harness.messages
  assert.equal(message.message, 'common.save_success')
  harness.click([message.element])
  assert.equal(harness.messages.size, 1, 'clicking the message itself must not close it')
  harness.click()
  assert.equal(harness.messages.size, 0, 'clicking elsewhere must close the save-success message')
  assert.equal(harness.listeners.size, 0, 'closing must release the document listener')
}

for (const platformTemplate of [false, true]) {
  test(`${platformTemplate ? 'platform template' : 'ordinary dashboard'} save can be dismissed outside`, () => {
    const harness = setup()
    Object.assign(harness.context, {
      canEditDashboard: { value: true },
      dashboardInfo: {
        value: { id: 'dashboard-1', name: 'Dashboard', dataState: 'saved', datasource: 'ds-1' },
      },
      props: { baseParams: { platformTemplate } },
      datasourceContext: { datasourceId: 'ds-1' },
      saveDashboardResource: (_params, callback) => callback(),
      savePlatformTemplateResource: (_params, callback) => callback(),
    })
    loadHandler('./Toolbar.vue', 'saveCanvasWithCheck', harness.context)()
    assertDismissible(harness)
  })
}

for (const newDashboard of [false, true]) {
  test(`${newDashboard ? 'new dashboard' : 'resource rename'} save can be dismissed outside`, () => {
    const harness = setup()
    let finished = false
    Object.assign(harness.context, {
      resource: { value: { validate: (callback) => callback(true) } },
      isTemplateCreateMode: { value: false },
      isNewDashboard: { value: newDashboard },
      canCreateBlankDashboard: { value: true },
      state: {
        id: 'dashboard-1',
        nodeType: 'leaf',
        opt: newDashboard ? 'newLeaf' : 'rename',
        datasource: 'ds-1',
      },
      resourceForm: { name: 'Dashboard', pid: 'root' },
      dashboardStore: { dashboardInfo: { dataState: 'saved' } },
      saveDashboardResource: (_params, callback) => callback({ id: 'dashboard-1' }),
      saveDashboardResourceTarget: (_params, _common, callback) => callback({ id: 'dashboard-1' }),
      emits: (event, payload) => {
        assert.equal(event, 'finish')
        assert.equal(payload.resourceId, 'dashboard-1')
        finished = true
      },
      resetForm() {},
    })
    loadHandler('../common/ResourceGroupOpt.vue', 'saveResource', harness.context)()
    assert.equal(finished, true, 'dismissible messages must not interrupt the save completion flow')
    assertDismissible(harness)
  })
}

test('tree-order save can be dismissed outside after persistence completes', async () => {
  const harness = setup()
  let completeSave
  Object.assign(harness.context, {
    canEditDashboardTree: { value: true },
    isTreeEditing: { value: true },
    saveTreeOrder: () =>
      new Promise((resolve) => {
        completeSave = resolve
      }),
  })
  const saving = loadHandler('../common/ResourceTree.vue', 'toggleTreeEditing', harness.context)()
  assert.equal(harness.messages.size, 0, 'no success message before persistence finishes')
  completeSave()
  await saving
  assert.equal(harness.context.isTreeEditing.value, false)
  assertDismissible(harness)
})

test('normal message closure releases its listener without closing other messages', () => {
  const harness = setup()
  vm.runInContext(
    "showDismissibleSuccess('first'); showDismissibleSuccess('second')",
    harness.context
  )
  const [first] = harness.messages
  first.close() // Same onClose callback used by the renderer's normal timeout.
  assert.equal(harness.listeners.size, 1)
  assert.equal(harness.messages.size, 1)
  harness.click()
  assert.equal(harness.messages.size, 0)
  assert.equal(harness.listeners.size, 0)
})
