import assert from 'node:assert/strict'
import fs from 'node:fs'
import test from 'node:test'

const source = fs.readFileSync(new URL('./ResourceTree.vue', import.meta.url), 'utf8')

test('places virtual dashboard group expand icons at the right edge', () => {
  assert.match(source, /:data-virtual-group="isVirtualNode\(data\) \? 'true' : undefined"/)
  assert.match(
    source,
    /\.dashboard-resource-tree[\s\S]*?\.ed-tree-node__content:has\(> \.custom-tree-node\[data-virtual-group='true'\]\)[\s\S]*?> \.ed-tree-node__expand-icon[\s\S]*?position: absolute;[\s\S]*?right: 8px;/
  )
  assert.match(
    source,
    /data-virtual-group='true'[\s\S]*?> \.ed-tree-node__expand-icon[\s\S]*?transform: rotate\(180deg\);/
  )
  assert.match(
    source,
    /data-virtual-group='true'[\s\S]*?> \.ed-tree-node__expand-icon\.expanded[\s\S]*?transform: rotate\(90deg\);/
  )
})

test('keeps virtual group labels and child dashboards in the intended hierarchy', () => {
  assert.match(
    source,
    /\.custom-tree-node[\s\S]*?data-virtual-group='true'[\s\S]*?padding-left: 0;/
  )
  assert.doesNotMatch(
    source,
    /data-virtual-group='true'[\s\S]*?> \.custom-tree-node[\s\S]*?> \.tree-node-icon[\s\S]*?display: none;/
  )
  assert.match(source, /> \.ed-tree-node:first-child:has\(/)
  assert.match(source, /\.ed-tree-node:first-child:has\([\s\S]*?> \.ed-tree-node__children[\s\S]*?margin: 0 0 8px !important;/)
  assert.match(source, /border-bottom: 1px solid var\(--workspace-border, #e5e7eb\);/)
  assert.match(source, /\.custom-tree-node\.is-leaf-node[\s\S]*?padding-left: 10px;/)
})
