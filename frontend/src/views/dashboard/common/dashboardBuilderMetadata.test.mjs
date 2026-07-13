import assert from 'node:assert/strict'
import esbuild from 'esbuild'

const build = await esbuild.build({
  entryPoints: ['src/views/dashboard/common/dashboardBuilderMetadata.ts'],
  bundle: true,
  platform: 'node',
  format: 'esm',
  write: false,
  absWorkingDir: process.cwd(),
})

const bundledSource = build.outputFiles[0].text
const moduleUrl = `data:text/javascript;base64,${Buffer.from(bundledSource).toString('base64')}`
const {
  buildDashboardBuilderMetadataCacheKey,
  buildTrackingEventCatalogFromConfig,
  clearDashboardBuilderMetadataCache,
  createFieldOptionIndex,
  getCachedDashboardBuilderMetadata,
} = await import(moduleUrl)

const cacheKey = buildDashboardBuilderMetadataCacheKey({
  datasourceId: 3,
  tenantId: 'tenant-a',
})

assert.equal(cacheKey, 'tenant-a:3', '缓存 key 应只按租户和数据源隔离')
assert.notEqual(
  cacheKey,
  buildDashboardBuilderMetadataCacheKey({ datasourceId: 3, tenantId: 'tenant-b' }),
  '不同租户不能复用同一个 builder metadata 缓存'
)

clearDashboardBuilderMetadataCache()
let loadCount = 0
const firstLoad = await getCachedDashboardBuilderMetadata(cacheKey, async () => {
  loadCount += 1
  return { schemaTables: [{ table_name: 'event' }], marker: 'first' }
})
const secondLoad = await getCachedDashboardBuilderMetadata(cacheKey, async () => {
  loadCount += 1
  return { schemaTables: [], marker: 'second' }
})

assert.equal(loadCount, 1, '同一 datasource + tenant 下重复打开弹窗应复用首次加载结果')
assert.equal(secondLoad, firstLoad, '重复读取应返回缓存中的同一个 metadata 对象')
assert.equal(secondLoad.marker, 'first')

const catalog = buildTrackingEventCatalogFromConfig({
  tenant_id: 'tenant-a',
  datasource_id: 3,
  default_event_table: 'event',
  default_event_name_field: 'event',
  event_name_mappings: [
    {
      event_name: 'ServerPayLog',
      event_display_name: '后端充值',
      event_category: 'Pay',
      collect_side: 'server',
      collectSide: 'client',
      properties: [
        {
          property_name: 'money',
          property_display_name: '金额',
          property_type: 'number',
          source_field: 'personal',
          json_path: '$.money',
        },
      ],
    },
  ],
})

assert.equal(catalog.datasource_id, 3)
assert.equal(catalog.groups.length, 1)
assert.equal(catalog.groups[0].label, 'Pay')
assert.equal(catalog.groups[0].events[0].value, 'tracking-event:event.event:ServerPayLog')
assert.equal('collect_side' in catalog.groups[0].events[0], false)
assert.equal('collectSide' in catalog.groups[0].events[0], false)
assert.equal(catalog.groups[0].events[0].properties[0].value, 'tracking-property:event.event:ServerPayLog:money')

const fieldIndex = createFieldOptionIndex({
  trackingEventOptions: [
    { value: 'tracking-event:event.event:ServerPayLog', field: 'event', label: '后端充值', table: 'event' },
  ],
  trackingEventPropertyOptions: [
    { value: 'tracking-property:event.event:ServerPayLog:money', field: 'money', label: '金额', table: 'event' },
  ],
  schemaFieldOptions: [
    { value: 'event.money', field: 'money', label: '物理金额', table: 'event' },
    { value: 'event.event', field: 'event', label: '事件名', table: 'event' },
  ],
})

assert.equal(
  fieldIndex.find('tracking-property:event.event:ServerPayLog:money')?.label,
  '金额',
  '字段索引应优先按 value 命中事件属性'
)
assert.equal(fieldIndex.find('money')?.label, '物理金额', '字段索引应保留 schema field 兜底查找')

console.log('dashboard builder metadata tests passed')
