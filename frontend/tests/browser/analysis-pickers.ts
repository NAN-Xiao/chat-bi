import { createApp, h, nextTick, ref } from 'vue'
import { createPinia } from 'pinia'
import { i18n } from '../../src/i18n'
import Editor from '../../src/views/dashboard/common/DashboardSqlEditor.vue'
import { dashboardApi } from '../../src/api/dashboard'
import { trackingConfigApi } from '../../src/api/system'
import '../../src/style.less'

// Mount the production editor with deterministic, datasource-scoped metadata.
const empty = new URLSearchParams(location.search).has('empty')

dashboardApi.execution_datasources = async () => [{ id: 1, name: 'Regression fixture', role: 'bound' }] as any
dashboardApi.execution_datasource_metadata = async () => ({ tables: [{
  table_name: 'events', table_role: 'event', fields: [
    { field_name: 'entity_id', field_type: 'varchar', field_role: 'entity_id' },
    { field_name: 'event_name', field_type: 'varchar', field_role: 'event_name' },
    { field_name: 'event_time', field_type: 'timestamp', field_role: 'event_time' },
    { field_name: 'amount', field_type: 'numeric' },
  ],
}] }) as any
trackingConfigApi.get = async () => ({ default_event_table: 'events', default_entity_id_field: 'entity_id' }) as any
trackingConfigApi.eventCatalog = async () => ({ event_table: 'events', event_name_field: 'event_name', groups: empty ? [] : [{ label: 'Events', events: [
  { event_name: 'start', display_name: 'Start' },
  { event_name: 'finish', display_name: 'Finish' },
] }] }) as any
const visible = ref(false)
const viewInfo = { datasource: 1, sql: '', chart: { type: 'table', source_config: { sourceTypes: ['sql'] } }, data: { fields: [], data: [] } }
createApp({ setup: () => () => [h('button', { onClick: () => visible.value = true }, 'Open editor'), h(Editor, { modelValue: visible.value, 'onUpdate:modelValue': (v: boolean) => visible.value = v, viewInfo, canEditSql: true })] })
  .use(createPinia()).use(i18n).mount('#app')
await nextTick()
visible.value = true
