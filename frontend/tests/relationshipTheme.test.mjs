import assert from 'node:assert/strict'
import { test } from 'node:test'
import { readFileSync, existsSync } from 'node:fs'
import vm from 'node:vm'
import ts from 'typescript'
function load() {
  const file = 'src/views/ds/relationshipTheme.ts'
  assert.ok(existsSync(file), 'relationship visuals must follow shared theme tokens')
  const exports = {}
  vm.runInNewContext(ts.transpileModule(readFileSync(file, 'utf8'), {
    compilerOptions: { module: ts.ModuleKind.CommonJS },
  }).outputText, { exports, structuredClone })
  return exports
}
test('saved generated port defaults become live theme tokens without changing field metadata', () => {
  const { normalizeGeneratedRelationshipPortStyles } = load()
  const ports = { groups: { list: { position: 'erPortPosition', attrs: {
    portBody: { stroke: '#DEE0E3', fill: '#ffffff', magnet: true },
    portNameLabel: { refX: 12 },
  } } }, items: [{ id: 'field-1', group: 'list', attrs: { portNameLabel: { text: 'Revenue' } } }] }
  const before = structuredClone(ports)
  const actual = normalizeGeneratedRelationshipPortStyles(ports)
  assert.equal(actual.groups.list.attrs.portBody.fill, 'var(--workspace-card-bg)')
  assert.equal(actual.groups.list.attrs.portBody.stroke, 'var(--workspace-border)')
  assert.equal(actual.groups.list.attrs.portNameLabel.fill, 'var(--workspace-text-primary)')
  assert.deepEqual(actual.items, ports.items)
  assert.deepEqual(ports, before)
})
test('explicit group and per-port colors survive, and unsaved port arrays remain untouched', () => {
  const { normalizeGeneratedRelationshipPortStyles } = load()
  const ports = { groups: { list: { attrs: { portBody: { fill: '#ffcc00', stroke: '#ff0000' }, portNameLabel: { fill: '#0000ff' } } } }, items: [{ id: '1', attrs: { portBody: { fill: '#abcdef' } } }] }
  assert.deepEqual(normalizeGeneratedRelationshipPortStyles(ports), ports)
  const newPorts = [{ id: 'new', group: 'list' }]
  assert.equal(normalizeGeneratedRelationshipPortStyles(newPorts), newPorts)
})
test('edge defaults follow theme while explicit colors and label metadata survive', () => {
  const { themeRelationshipEdgeAttrs } = load()
  const custom = { line: { stroke: '#dd2200', strokeWidth: 4 }, label: { text: 'join' } }
  assert.deepEqual(themeRelationshipEdgeAttrs(custom), custom)
  assert.equal(themeRelationshipEdgeAttrs({ line: { stroke: '#DEE0E3' } }).line.stroke, 'var(--workspace-border)')
})
test('theme refresh updates existing views without touching graph geometry or serialized configuration', () => {
  const { refreshRelationshipTheme } = load()
  const seen = []
  const node = { findView: () => ({ isNodeView: () => true, isEdgeView: () => false, update: () => seen.push('node') }) }
  const edge = { findView: () => ({ isNodeView: () => false, isEdgeView: () => true, update: () => seen.push('edge') }) }
  const graph = { getNodes: () => [node], getEdges: () => [edge] }
  refreshRelationshipTheme(graph)
  assert.deepEqual(seen, ['node', 'edge'])
  refreshRelationshipTheme(null)
})

test('component subscribes and disposes with its own graph canvas', () => {
  const source = readFileSync('src/views/ds/TableRelationship.vue', 'utf8')
  assert.match(source, /unsubscribeTheme = subscribeTheme\(\(\) => refreshRelationshipTheme\(graph\)\)/)
  assert.match(source, /onBeforeUnmount\(\(\) => \{\s*unsubscribeTheme\?\.\(\)/)
  assert.match(source, /container: relationshipCanvas\.value/)
  assert.doesNotMatch(source, /document\.getElementById\('container'\)/)
})
