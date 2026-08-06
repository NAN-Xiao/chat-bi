<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { getPermissionDatasources, getPermissionDatasourceTables, type PermissionDatasourceOption } from '@/api/permissions'
import { trackingConfigApi } from '@/api/system'

export type MetadataPermissionType = 'schema' | 'event' | 'event_property'
export type MetadataPermissionTarget = {
  catalog_key?: string
  schema_key?: string
  event_name?: string
  event_property_key?: string
  enable: boolean
}

const props = defineProps<{
  modelValue: boolean
  permissionType: MetadataPermissionType
  initialTarget?: MetadataPermissionTarget | null
}>()
const emit = defineEmits<{
  (event: 'update:modelValue', value: boolean): void
  (event: 'save', value: { type: MetadataPermissionType; ds_id: number | string; ds_name: string; target: MetadataPermissionTarget; name: string }): void
}>()

const loading = ref(false)
const datasourceOptions = ref<PermissionDatasourceOption[]>([])
const tableOptions = ref<any[]>([])
const eventGroups = ref<any[]>([])
const datasource = ref<PermissionDatasourceOption | null>(null)
const target = ref<MetadataPermissionTarget>({ enable: false })

const visible = computed({
  get: () => props.modelValue,
  set: (value: boolean) => emit('update:modelValue', value),
})
const title = computed(() => {
  if (props.permissionType === 'schema') return '设置 Schema 权限'
  if (props.permissionType === 'event') return '设置事件权限'
  return '设置事件属性权限'
})
const schemaOptions = computed(() => {
  const seen = new Set<string>()
  return tableOptions.value
    .map((item) => ({ catalog_key: String(item.catalog_key || ''), schema_key: String(item.schema_key || ''), label: `${item.catalog_name || item.catalog_key || '-'} / ${item.schema_name || item.schema_key || '-'}` }))
    .filter((item) => {
      const key = `${item.catalog_key}:${item.schema_key}`
      if (!item.schema_key || seen.has(key)) return false
      seen.add(key)
      return true
    })
})
const eventOptions = computed(() => eventGroups.value.flatMap((group) => group.events || []))
const selectedEvent = computed(() => eventOptions.value.find((item) => item.event_name === target.value.event_name))
const propertyOptions = computed(() => selectedEvent.value?.properties || [])

function resetTarget() {
  target.value = { enable: false, ...(props.initialTarget || {}) }
}

function handleSchemaChange(schemaKey: string) {
  const schema = schemaOptions.value.find((item) => item.schema_key === schemaKey)
  target.value.catalog_key = schema?.catalog_key || ''
}

async function loadTargets() {
  if (!datasource.value) return
  try {
    if (props.permissionType === 'schema') {
      tableOptions.value = await getPermissionDatasourceTables(datasource.value.id, props.permissionType)
    } else {
      const catalog = await trackingConfigApi.eventCatalog(datasource.value.id)
      eventGroups.value = catalog?.groups || []
    }
  } catch (error) {
    console.error(error)
    tableOptions.value = []
    eventGroups.value = []
    ElMessage.error('无法读取所选数据源的权限对象，请确认数据源绑定后重试。')
  }
}

async function loadOptions() {
  if (!props.modelValue) return
  loading.value = true
  try {
    datasourceOptions.value = await getPermissionDatasources(props.permissionType)
    datasource.value = datasourceOptions.value.find((item) => String(item.id) === String((props.initialTarget as any)?.ds_id)) || datasourceOptions.value[0] || null
    await loadTargets()
  } catch (error) {
    console.error(error)
    datasourceOptions.value = []
    ElMessage.error('无法读取可用数据源，请刷新后重试。')
  } finally {
    loading.value = false
  }
}

function saveTarget() {
  if (!datasource.value) {
    ElMessage.warning('请选择数据源')
    return
  }
  const label = props.permissionType === 'schema'
    ? `Schema：${target.value.schema_key || ''}`
    : props.permissionType === 'event'
      ? `事件：${target.value.event_name || ''}`
      : `事件属性：${target.value.event_name || ''}.${target.value.event_property_key || ''}`
  if (!label.split('：')[1]) {
    ElMessage.warning('请选择权限对象')
    return
  }
  emit('save', {
    type: props.permissionType,
    ds_id: datasource.value.id,
    ds_name: datasource.value.name,
    target: { ...target.value, enable: false },
    name: label,
  })
  visible.value = false
}

watch(() => props.modelValue, (value) => {
  if (value) {
    resetTarget()
    loadOptions()
  }
})
watch(() => props.initialTarget, resetTarget, { deep: true })
onMounted(loadOptions)
</script>

<template>
  <el-dialog v-model="visible" :title="title" width="560px" destroy-on-close>
    <el-form v-loading="loading" label-position="top" @submit.prevent>
      <el-form-item label="数据源" required>
        <el-select v-model="datasource" value-key="id" filterable style="width: 100%" @change="loadTargets">
          <el-option v-for="item in datasourceOptions" :key="item.id" :label="item.name" :value="item" />
        </el-select>
      </el-form-item>
      <el-form-item v-if="permissionType === 'schema'" label="Schema" required>
        <el-select v-model="target.schema_key" filterable style="width: 100%" placeholder="请选择 Schema" @change="handleSchemaChange">
          <el-option v-for="item in schemaOptions" :key="`${item.catalog_key}:${item.schema_key}`" :label="item.label" :value="item.schema_key" />
        </el-select>
      </el-form-item>
      <template v-else>
        <el-form-item label="事件" required>
          <el-select v-model="target.event_name" filterable style="width: 100%" placeholder="请选择事件">
            <el-option v-for="item in eventOptions" :key="item.event_name" :label="item.display_name || item.event_name" :value="item.event_name" />
          </el-select>
        </el-form-item>
        <el-form-item v-if="permissionType === 'event_property'" label="事件属性" required>
          <el-select v-model="target.event_property_key" filterable style="width: 100%" placeholder="请选择事件属性">
            <el-option v-for="item in propertyOptions" :key="item.value || item.property_name" :label="item.display_name || item.property_name" :value="item.property_name" />
          </el-select>
        </el-form-item>
      </template>
      <el-alert title="权限对象仅提交稳定键，页面名称只用于展示。" type="info" :closable="false" />
    </el-form>
    <template #footer>
      <el-button @click="visible = false">取消</el-button>
      <el-button type="primary" @click="saveTarget">保存</el-button>
    </template>
  </el-dialog>
</template>
