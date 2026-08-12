import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'
import ts from 'typescript'

async function loadLifecycleModule() {
  const source = readFileSync('src/views/chat/component/floatingTooltipLifecycle.ts', 'utf8')
  const compiled = ts.transpileModule(source, {
    compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 },
  }).outputText
  const moduleUrl = `data:text/javascript;base64,${Buffer.from(compiled).toString('base64')}`
  return import(moduleUrl)
}

class FakeEventTarget {
  listeners = new Map()

  addEventListener(type, listener, options) {
    const entries = this.listeners.get(type) || []
    entries.push({ listener, options })
    this.listeners.set(type, entries)
  }

  removeEventListener(type, listener, options) {
    const entries = this.listeners.get(type) || []
    this.listeners.set(
      type,
      entries.filter((entry) => entry.listener !== listener || entry.options !== options)
    )
  }

  dispatch(type, event = {}) {
    for (const { listener } of this.listeners.get(type) || []) {
      listener(event)
    }
  }
}

function createEnvironment() {
  const ownerWindow = new FakeEventTarget()
  const ownerDocument = new FakeEventTarget()
  ownerDocument.defaultView = ownerWindow
  ownerDocument.hidden = false
  const insideTarget = {}
  const mount = new FakeEventTarget()
  mount.ownerDocument = ownerDocument
  mount.contains = (target) => target === insideTarget
  return { mount, ownerDocument, ownerWindow, insideTarget }
}

test('floating tooltip closes on every boundary that can detach it from its chart', async () => {
  const { bindFloatingTooltipDismissal } = await loadLifecycleModule()
  const { mount, ownerDocument, ownerWindow } = createEnvironment()
  let hiddenCount = 0
  bindFloatingTooltipDismissal({ mount, hide: () => hiddenCount++ })

  mount.dispatch('pointerleave')
  ownerDocument.dispatch('pointerdown', { target: {} })
  ownerDocument.dispatch('scroll')
  ownerDocument.dispatch('keydown', { key: 'Escape' })
  ownerWindow.dispatch('blur')
  ownerWindow.dispatch('pagehide')
  ownerDocument.hidden = true
  ownerDocument.dispatch('visibilitychange')

  assert.equal(hiddenCount, 7)
})

test('inside clicks and visible-page changes keep the active tooltip intact', async () => {
  const { bindFloatingTooltipDismissal } = await loadLifecycleModule()
  const { mount, ownerDocument, insideTarget } = createEnvironment()
  let hiddenCount = 0
  bindFloatingTooltipDismissal({ mount, hide: () => hiddenCount++ })

  ownerDocument.dispatch('pointerdown', { target: insideTarget })
  ownerDocument.dispatch('keydown', { key: 'Enter' })
  ownerDocument.dispatch('visibilitychange')

  assert.equal(hiddenCount, 0)
})

test('cleanup removes all tooltip dismissal listeners', async () => {
  const { bindFloatingTooltipDismissal } = await loadLifecycleModule()
  const { mount, ownerDocument, ownerWindow } = createEnvironment()
  let hiddenCount = 0
  const cleanup = bindFloatingTooltipDismissal({ mount, hide: () => hiddenCount++ })

  cleanup()
  mount.dispatch('pointerleave')
  ownerDocument.dispatch('pointerdown', { target: {} })
  ownerDocument.dispatch('scroll')
  ownerDocument.dispatch('keydown', { key: 'Escape' })
  ownerDocument.hidden = true
  ownerDocument.dispatch('visibilitychange')
  ownerWindow.dispatch('blur')
  ownerWindow.dispatch('pagehide')

  assert.equal(hiddenCount, 0)
})

test('BaseG2Chart binds and tears down the shared floating tooltip lifecycle', () => {
  const source = readFileSync('src/views/chat/component/BaseG2Chart.ts', 'utf8')

  assert.match(source, /bindFloatingTooltipDismissal\(\{[\s\S]*?hide:\s*\(\)\s*=>\s*this\.hideTooltip\(\)/)
  assert.match(source, /render\(\)\s*\{[\s\S]*?this\.hideTooltip\(\)[\s\S]*?this\.chart\?\.render\(\)/)
  assert.match(source, /destroy\(\)\s*\{[\s\S]*?this\.hideTooltip\(\)[\s\S]*?removeTooltipDismissalListeners\?\.\(\)[\s\S]*?this\.chart\?\.destroy\(\)/)
})
