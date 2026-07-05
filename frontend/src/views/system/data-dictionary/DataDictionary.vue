<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { ElMessage } from 'element-plus'
import { Delete, Download, Plus, Refresh, Upload } from '@element-plus/icons-vue'
import { datasourceApi } from '@/api/datasource'
import { trackingConfigApi } from '@/api/system'
import EmptyBackground from '@/views/dashboard/common/EmptyBackground.vue'
import icon_searchOutline_outlined from '@/assets/svg/icon_search-outline_outlined.svg'

type DatasourceItem = {
  id: number | string
  name: string
  description?: string
  type?: string
  type_name?: string
  num?: string
}

type SchemaField = {
  id: number | string
  field_name: string
  field_type?: string
  field_comment?: string
  custom_comment?: string
  checked?: boolean
  field_index?: number
  display_name?: string
  field_role?: string
  semantic_type?: string
  aliases?: string[]
  expression?: string
  source_field?: string
  json_path?: string
  is_json_subfield?: boolean
  category?: string
  value_mappings?: any[] | Record<string, any>
  example_values?: any[]
}

type FieldValueMapping = {
  value: string
  display_name?: string
  category?: string
  description?: string
}

type SchemaTable = {
  id: number | string
  table_name: string
  table_comment?: string
  custom_comment?: string
  checked?: boolean
  fields: SchemaField[]
}

type SchemaMetadata = DatasourceItem & {
  tables: SchemaTable[]
}

type SchemaChangeField = {
  field_name: string
  field_type: string
  field_comment?: string
  required?: boolean
}

type TrackingConfig = {
  enabled?: boolean
  default_event_table?: string
  default_subject_field?: string
  default_event_name_field?: string
  default_event_time_field?: string
  field_role_mappings?: any[]
  event_name_mappings?: any[]
  sql_rules?: string
  notes?: string
  tables?: any[]
  fields?: any[]
}

const { t } = useI18n()

const datasourceLoading = ref(false)
const schemaLoading = ref(false)
const changeSubmitting = ref(false)
const templateDownloading = ref(false)
const dictionaryExporting = ref(false)
const dictionaryImporting = ref(false)
const tableKeyword = ref('')
const fieldKeyword = ref('')
const datasources = ref<DatasourceItem[]>([])
const schema = ref<SchemaMetadata | null>(null)
const selectedTableId = ref<number | string | null>(null)
const activeFieldView = ref('all')
const changeDrawerVisible = ref(false)
const dictionaryFieldDrawerVisible = ref(false)
const changeMode = ref<'create_table' | 'create_field' | 'alter_field'>('create_table')
const dictionaryMode = ref<'create' | 'edit'>('create')
const changeFormRef = ref()
const dictionaryFormRef = ref()
const changeForm = reactive({
  change_type: 'create_table' as 'create_table' | 'alter_table',
  table_name: '',
  table_comment: '',
  request_comment: '',
  source_table_name: '',
  fields: [] as SchemaChangeField[],
})
const dictionarySubmitting = ref(false)
const trackingConfig = ref<TrackingConfig | null>(null)
const dictionaryForm = reactive({
  table_name: '',
  field_name: '',
  field_comment: '',
  field_role: '',
  semantic_type: '',
  source_field: '',
  json_path: '',
  aliases_text: '',
  expression: '',
  example_values_text: '',
  ai_notes: '',
})

const changeFormRules = {
  table_name: [{ required: true, message: t('data_dictionary.table_name_required'), trigger: 'blur' }],
}

const dictionaryFormRules = {
  table_name: [{ required: true, message: t('data_dictionary.table_name_required'), trigger: 'blur' }],
  field_name: [{ required: true, message: t('data_dictionary.dictionary_field_name_required'), trigger: 'blur' }],
}

const fieldTypeOptions = [
  'text',
  'varchar(255)',
  'integer',
  'bigint',
  'numeric',
  'double precision',
  'boolean',
  'date',
  'timestamp',
  'timestamp with time zone',
  'jsonb',
].map((value) => ({ label: value, value }))

const dictionaryRoleOptions = [
  'event_time',
  'partition_date',
  'snapshot_date',
  'event_name',
  'subject_id',
  'json_path_dimension',
  'json_path_metric',
  'json_path_flag',
  'dimension_json',
  'event_params_json',
  'profile_json',
  'payment_json',
  'retention_json',
].map((value) => ({ label: value, value }))

const semanticTypeOptions = [
  'date',
  'timestamp_ms',
  'identifier',
  'text',
  'number',
  'json',
  'boolean_flag',
  'country_code',
].map((value) => ({ label: value, value }))

const inferSourceField = (fieldName: string) => {
  const text = String(fieldName || '').trim()
  return text.includes('.') ? text.split('.', 1)[0] : ''
}

const inferJsonPath = (fieldName: string) => {
  const text = String(fieldName || '').trim()
  return text.includes('.') ? `$.${text.split('.').slice(1).join('.')}` : ''
}

const syncJsonSourceFromFieldName = () => {
  if (dictionaryForm.source_field && dictionaryForm.json_path) return
  const sourceField = inferSourceField(dictionaryForm.field_name)
  const jsonPath = inferJsonPath(dictionaryForm.field_name)
  if (sourceField && !dictionaryForm.source_field) {
    dictionaryForm.source_field = sourceField
  }
  if (jsonPath && !dictionaryForm.json_path) {
    dictionaryForm.json_path = jsonPath
  }
}

const filteredTables = computed(() => {
  const keyword = tableKeyword.value.trim().toLowerCase()
  const tables = schema.value?.tables || []
  if (!keyword) return tables
  return tables.filter((item) => {
    return [item.table_name, item.table_comment, item.custom_comment].some((value) =>
      String(value || '').toLowerCase().includes(keyword)
    )
  })
})

const selectedTable = computed(() => {
  return filteredTables.value.find((item) => String(item.id) === String(selectedTableId.value)) || null
})

const sourceFieldName = (field: SchemaField) => field.source_field || inferSourceField(field.field_name)

const physicalFieldOptions = computed(() => {
  return (selectedTable.value?.fields || [])
    .filter((item) => !isDictionaryField(item))
    .map((item) => ({
      label: item.field_name,
      value: item.field_name,
      type: item.field_type || '',
    }))
})

const isJsonSourceField = (field: SchemaField) => {
  const text = [
    field.field_type,
    field.field_role,
    field.semantic_type,
    field.category,
  ].join(' ').toLowerCase()
  return text.includes('json')
}

const nestedViewOptions = computed(() => {
  const fields = selectedTable.value?.fields || []
  const physicalByName = new Map(
    fields
      .filter((item) => !isDictionaryField(item) && item.field_name)
      .map((item) => [item.field_name, item])
  )
  const sourceNames = new Set<string>()
  fields.forEach((field) => {
    if (!field.field_name) return
    if (!isDictionaryField(field) && isJsonSourceField(field)) {
      sourceNames.add(field.field_name)
      return
    }
    if (isDictionaryField(field)) {
      const source = sourceFieldName(field)
      if (source) sourceNames.add(source)
    }
  })
  return Array.from(sourceNames)
    .filter((source) => physicalByName.has(source))
    .sort((left, right) => left.localeCompare(right))
    .map((source) => {
      const field = physicalByName.get(source)
      return {
        label: field?.display_name || field?.custom_comment || field?.field_comment || source,
        value: `json:${source}`,
        source,
      }
    })
})

const fieldViewOptions = computed(() => [
  { label: t('data_dictionary.all_fields'), value: 'all' },
  { label: t('data_dictionary.physical_fields'), value: 'physical' },
  ...nestedViewOptions.value.map((item) => ({
    label: item.label === item.source ? `JSON: ${item.source}` : `JSON: ${item.source} (${item.label})`,
    value: item.value,
  })),
])

const filteredFields = computed(() => {
  const keyword = fieldKeyword.value.trim().toLowerCase()
  const table = selectedTable.value
  let fields = table?.fields || []
  if (activeFieldView.value === 'physical') {
    fields = fields.filter((item) => !isDictionaryField(item))
  } else if (activeFieldView.value.startsWith('json:')) {
    const source = activeFieldView.value.slice('json:'.length)
    fields = fields.filter((item) => {
      if (!item.field_name) return false
      if (!isDictionaryField(item)) return item.field_name === source
      return sourceFieldName(item) === source
    })
  }
  if (!keyword) return fields
  return fields.filter((item) => {
    return [
      item.field_name,
      item.display_name,
      item.field_type,
      item.field_role,
      item.semantic_type,
      item.field_comment,
      item.custom_comment,
      item.expression,
      item.source_field,
      item.json_path,
    ].some((value) => String(value || '').toLowerCase().includes(keyword))
  })
})

const isDictionaryField = (field: SchemaField) =>
  field.is_json_subfield || String(field.id || '').startsWith('tracking:')

const fieldDisplayName = (field: SchemaField) => field.display_name || field.field_name

const fieldSourceLabel = (field: SchemaField) => {
  if (isDictionaryField(field)) return t('data_dictionary.dictionary_field')
  if (fieldValueMappings(field).length) return t('data_dictionary.value_dictionary_field')
  return t('data_dictionary.physical_field')
}

const fieldSourceTagType = (field: SchemaField) => {
  if (isDictionaryField(field)) return 'success'
  if (fieldValueMappings(field).length) return 'warning'
  return 'info'
}

const fieldTypeLabel = (field: SchemaField) => field.semantic_type || field.field_type || '-'

const eventNamesFromMapping = (item: any): string[] => {
  if (!item) return []
  if (typeof item !== 'object') return [String(item)].filter(Boolean)
  const names: string[] = []
  ;['event_name', 'name', 'value'].forEach((key) => {
    if (item[key]) names.push(String(item[key]))
  })
  if (Array.isArray(item.events)) {
    item.events.forEach((value: any) => {
      if (value) names.push(String(value))
    })
  }
  return Array.from(new Set(names))
}

const eventDisplayName = (item: any, value: string) => {
  if (!item || typeof item !== 'object') return value
  return item.event_display_name || item.display_name || item.metric || item.name || value
}

const eventDescription = (item: any) => {
  if (!item || typeof item !== 'object') return ''
  return item.description || item.event_description || item.ai_notes || ''
}

const eventCategory = (item: any) => {
  if (!item || typeof item !== 'object') return ''
  return item.event_category || item.category || item.metric || ''
}

const eventValueMappingsForField = (field: SchemaField): FieldValueMapping[] => {
  if (field.field_role !== 'event_name') return []
  const current = trackingConfig.value
  if (!current?.default_event_name_field) return []
  const selectedTableName = selectedTable.value?.table_name || ''
  if (current.default_event_table && current.default_event_table !== selectedTableName) return []
  if (current.default_event_name_field !== field.field_name) return []
  return (current.event_name_mappings || []).flatMap((item: any) =>
    eventNamesFromMapping(item).map((value) => ({
      value,
      display_name: eventDisplayName(item, value),
      category: eventCategory(item),
      description: eventDescription(item),
    }))
  )
}

const fieldValueMappings = (field: SchemaField): FieldValueMapping[] => {
  const eventValues = eventValueMappingsForField(field)
  if (eventValues.length) return eventValues
  const values = field.value_mappings
  if (Array.isArray(values)) {
    return values.map((item: any) => {
      if (item && typeof item === 'object') {
        const value = String(item.value || item.name || item.event_name || item.key || '')
        return {
          value,
          display_name: item.display_name || item.label || item.name || value,
          category: item.category || item.metric || '',
          description: item.description || item.ai_notes || '',
        }
      }
      const text = String(item || '')
      const [value, displayName] = text.includes('=') ? text.split(/=(.*)/s, 2).map((part) => part.trim()) : [text, '']
      return { value, display_name: displayName || value }
    }).filter((item) => item.value)
  }
  if (values && typeof values === 'object') {
    return Object.entries(values).map(([value, displayName]) => ({
      value,
      display_name: String(displayName || value),
    }))
  }
  return []
}

const fieldRowClassName = ({ row }: { row: SchemaField }) =>
  fieldValueMappings(row).length ? 'field-row--has-values' : 'field-row--no-values'

const changeDrawerTitle = computed(() =>
  changeMode.value === 'create_table'
    ? t('data_dictionary.create_table')
    : changeMode.value === 'create_field'
      ? t('data_dictionary.create_field')
    : t('data_dictionary.alter_field')
)

const selectFirstVisibleTable = () => {
  selectedTableId.value = filteredTables.value[0]?.id ?? null
}

const loadTrackingConfig = async () => {
  trackingConfig.value = await trackingConfigApi.get()
}

const currentTrackingConfig = async () => {
  if (!trackingConfig.value) {
    await loadTrackingConfig()
  }
  return trackingConfig.value || {}
}

const emptyField = (): SchemaChangeField => ({
  field_name: '',
  field_type: 'text',
  field_comment: '',
  required: false,
})

const loadSchema = async (id: number | string) => {
  schemaLoading.value = true
  fieldKeyword.value = ''
  tableKeyword.value = ''
  selectedTableId.value = null
  try {
    const [schemaRes] = await Promise.all([
      datasourceApi.schemaMetadata(id),
      loadTrackingConfig().catch(() => {
        trackingConfig.value = null
      }),
    ])
    schema.value = schemaRes
    selectFirstVisibleTable()
  } finally {
    schemaLoading.value = false
  }
}

const loadDatasources = async () => {
  datasourceLoading.value = true
  try {
    const res = await datasourceApi.accessibleList()
    datasources.value = Array.isArray(res) ? res : []
    if (datasources.value.length) {
      await loadSchema(datasources.value[0].id)
    } else {
      schema.value = null
    }
  } finally {
    datasourceLoading.value = false
  }
}

onMounted(() => {
  loadDatasources()
})

watch(selectedTableId, () => {
  activeFieldView.value = 'all'
})

const splitTextList = (value: string) =>
  String(value || '')
    .split(/[\n,，]/)
    .map((item) => item.trim())
    .filter(Boolean)

const saveBlob = (blob: Blob, filename: string) => {
  const url = window.URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)
  window.URL.revokeObjectURL(url)
}

const downloadTrackingTemplate = async () => {
  templateDownloading.value = true
  try {
    const blob = await trackingConfigApi.downloadTemplate()
    saveBlob(blob, 'tracking_dictionary_template.xlsx')
    ElMessage.success(t('data_dictionary.template_downloaded'))
  } finally {
    templateDownloading.value = false
  }
}

const exportTrackingConfig = async () => {
  dictionaryExporting.value = true
  try {
    const blob = await trackingConfigApi.exportExcel()
    saveBlob(blob, 'tracking_dictionary_current.xlsx')
    ElMessage.success(t('data_dictionary.export_downloaded'))
  } finally {
    dictionaryExporting.value = false
  }
}

const importTrackingExcel = async (options: any) => {
  dictionaryImporting.value = true
  try {
    const result: any = await trackingConfigApi.importExcel(options.file)
    trackingConfig.value = result?.config || result
    const summary = result?.summary || {}
    ElMessage.success(t('data_dictionary.import_success', {
      tables: summary.table_count || 0,
      fields: summary.field_count || 0,
      events: summary.event_count || 0,
    }))
    if (summary.warning_count) {
      const firstWarning = Array.isArray(summary.warnings) ? summary.warnings[0] : ''
      ElMessage.warning(
        firstWarning
          ? t('data_dictionary.import_warning_with_first', { count: summary.warning_count, warning: firstWarning })
          : t('data_dictionary.import_warning', { count: summary.warning_count })
      )
    }
    if (schema.value?.id) {
      await loadSchema(schema.value.id)
    } else {
      await loadDatasources()
    }
    options.onSuccess?.(result)
  } catch (error) {
    options.onError?.(error)
  } finally {
    dictionaryImporting.value = false
  }
}

const dictionaryPayload = async () => {
  const current = await currentTrackingConfig()
  const fields = Array.isArray(current.fields) ? [...current.fields] : []
  const tableName = dictionaryForm.table_name.trim()
  const fieldName = dictionaryForm.field_name.trim()
  const nextField = {
    table_name: tableName,
    field_name: fieldName,
    field_comment: dictionaryForm.field_comment.trim(),
    field_role: dictionaryForm.field_role.trim(),
    semantic_type: dictionaryForm.semantic_type.trim(),
    source_field: dictionaryForm.source_field.trim(),
    json_path: dictionaryForm.json_path.trim(),
    aliases: splitTextList(dictionaryForm.aliases_text),
    expression: dictionaryForm.expression.trim(),
    required: false,
    example_values: splitTextList(dictionaryForm.example_values_text),
    ai_notes: dictionaryForm.ai_notes.trim(),
  }
  const existingIndex = fields.findIndex(
    (item: any) => item?.table_name === tableName && item?.field_name === fieldName
  )
  if (existingIndex >= 0) {
    fields.splice(existingIndex, 1, { ...fields[existingIndex], ...nextField })
  } else {
    fields.push(nextField)
  }

  const tables = Array.isArray(current.tables) ? [...current.tables] : []
  if (!tables.some((item: any) => item?.table_name === tableName)) {
    const table = schema.value?.tables.find((item) => item.table_name === tableName)
    tables.push({
      table_name: tableName,
      table_comment: table?.custom_comment || table?.table_comment || '',
      table_role: '',
      aliases: [],
      ai_notes: '',
    })
  }

  return trackingConfigPayload(current, fields, tables)
}

const trackingConfigPayload = (
  current: TrackingConfig,
  fields: any[],
  tables = Array.isArray(current.tables) ? [...current.tables] : []
) => ({
  enabled: current.enabled !== false,
  default_event_table: current.default_event_table || '',
  default_subject_field: current.default_subject_field || '',
  default_event_name_field: current.default_event_name_field || '',
  default_event_time_field: current.default_event_time_field || '',
  field_role_mappings: Array.isArray(current.field_role_mappings) ? current.field_role_mappings : [],
  event_name_mappings: Array.isArray(current.event_name_mappings) ? current.event_name_mappings : [],
  sql_rules: current.sql_rules || '',
  notes: current.notes || '',
  tables,
  fields,
})

const submitDictionaryField = async () => {
  if (!schema.value) return
  const valid = await dictionaryFormRef.value?.validate?.().catch(() => false)
  if (!valid) return
  dictionarySubmitting.value = true
  try {
    const payload = await dictionaryPayload()
    trackingConfig.value = await trackingConfigApi.update(payload)
    ElMessage.success(t('data_dictionary.dictionary_field_saved'))
    dictionaryFieldDrawerVisible.value = false
    await loadSchema(schema.value.id)
  } finally {
    dictionarySubmitting.value = false
  }
}

const addChangeField = () => {
  changeForm.fields.push(emptyField())
}

const removeChangeField = (index: number) => {
  if (changeForm.fields.length <= 1) return
  changeForm.fields.splice(index, 1)
}

const submitSchemaChange = async () => {
  if (!schema.value) return
  const valid = await changeFormRef.value?.validate?.().catch(() => false)
  if (!valid) return
  const fields = changeForm.fields
    .map((field) => ({
      field_name: field.field_name.trim(),
      field_type: field.field_type.trim(),
      field_comment: field.field_comment?.trim(),
      required: !!field.required,
    }))
    .filter((field) => field.field_name || field.field_type || field.field_comment)
  if (!fields.length || fields.some((field) => !field.field_name || !field.field_type)) {
    ElMessage.warning(t('data_dictionary.field_required'))
    return
  }
  changeSubmitting.value = true
  try {
    await datasourceApi.submitSchemaChange(schema.value.id, {
      change_type: changeForm.change_type,
      table_name: changeForm.table_name.trim(),
      table_comment: changeForm.table_comment.trim(),
      source_table_name: changeForm.change_type === 'alter_table' ? changeForm.source_table_name : undefined,
      request_comment: changeForm.request_comment.trim(),
      fields,
    })
    ElMessage.success(t('data_dictionary.schema_change_submitted'))
    changeDrawerVisible.value = false
  } finally {
    changeSubmitting.value = false
  }
}
</script>

<template>
  <div v-loading="schemaLoading" class="data-dictionary-container professional-container">
      <aside class="dictionary-sidebar">
        <template v-if="schema">
          <div class="table-toolbar">
            <div class="panel-head">
              <span>{{ t('ds.tables') }}</span>
              <span class="muted">{{ filteredTables.length }}</span>
            </div>
            <el-input
              v-model="tableKeyword"
              class="table-search"
              clearable
              :placeholder="t('data_dictionary.search_table')"
              @input="selectFirstVisibleTable"
            >
              <template #prefix>
                <el-icon>
                  <icon_searchOutline_outlined />
                </el-icon>
              </template>
            </el-input>
          </div>

          <div class="table-list">
            <button
              v-for="table in filteredTables"
              :key="table.id"
              type="button"
              class="table-item"
              :class="{ active: String(selectedTableId) === String(table.id) }"
              @click="selectedTableId = table.id"
            >
              <span class="table-name">{{ table.table_name }}</span>
              <span class="table-comment">{{ table.custom_comment || table.table_comment || '-' }}</span>
            </button>
            <EmptyBackground
              v-if="!filteredTables.length"
              :description="t('data_dictionary.empty_table')"
              img-type="tree"
            />
          </div>
        </template>

        <EmptyBackground
          v-else
          class="sidebar-empty"
          :description="t('data_dictionary.empty_datasource')"
          img-type="noneWhite"
        />
      </aside>

      <main class="dictionary-detail">
        <template v-if="schema">
          <div class="detail-head">
            <div class="field-toolbar">
              <el-input
                v-model="fieldKeyword"
                class="field-search"
                clearable
                :placeholder="t('data_dictionary.search_field')"
              >
                <template #prefix>
                  <el-icon>
                    <icon_searchOutline_outlined />
                  </el-icon>
                </template>
              </el-input>
              <el-select
                v-model="activeFieldView"
                class="field-view-select"
                :placeholder="t('data_dictionary.field_view')"
              >
                <el-option
                  v-for="option in fieldViewOptions"
                  :key="option.value"
                  :label="option.label"
                  :value="option.value"
                />
              </el-select>
            </div>
            <div class="schema-actions">
              <el-button :icon="Download" :loading="templateDownloading" @click="downloadTrackingTemplate">
                {{ t('data_dictionary.download_template') }}
              </el-button>
              <el-button :icon="Download" :loading="dictionaryExporting" @click="exportTrackingConfig">
                {{ t('data_dictionary.export_dictionary') }}
              </el-button>
              <el-upload
                accept=".xlsx,.xls"
                :show-file-list="false"
                :http-request="importTrackingExcel"
              >
                <el-button :icon="Upload" :loading="dictionaryImporting">
                  {{ t('data_dictionary.import_dictionary') }}
                </el-button>
              </el-upload>
            </div>
          </div>

          <section class="field-panel">
            <el-table
              :data="filteredFields"
              class="field-table"
              style="width: 100%"
              :row-class-name="fieldRowClassName"
            >
              <el-table-column type="expand" width="46">
                <template #default="scope">
                  <div v-if="fieldValueMappings(scope.row).length" class="field-value-panel">
                    <div class="field-value-head">
                      <span>{{ t('data_dictionary.field_value_dictionary') }}</span>
                      <span class="muted">{{ fieldValueMappings(scope.row).length }}</span>
                    </div>
                    <el-table
                      :data="fieldValueMappings(scope.row)"
                      class="field-value-table"
                      size="small"
                    >
                      <el-table-column prop="value" :label="t('data_dictionary.field_value')" min-width="180" show-overflow-tooltip />
                      <el-table-column prop="display_name" :label="t('data_dictionary.field_value_display_name')" min-width="180" show-overflow-tooltip />
                      <el-table-column prop="category" :label="t('data_dictionary.field_value_category')" min-width="160" show-overflow-tooltip>
                        <template #default="valueScope">
                          {{ valueScope.row.category || '-' }}
                        </template>
                      </el-table-column>
                      <el-table-column prop="description" :label="t('data_dictionary.field_value_description')" min-width="360" show-overflow-tooltip>
                        <template #default="valueScope">
                          {{ valueScope.row.description || '-' }}
                        </template>
                      </el-table-column>
                    </el-table>
                  </div>
                  <div v-else class="field-value-empty">
                    {{ t('data_dictionary.empty_field_value_dictionary') }}
                  </div>
                </template>
              </el-table-column>
              <el-table-column :label="t('datasource.field_name')" min-width="220" show-overflow-tooltip>
                <template #default="scope">
                  <div class="field-name-cell">
                    <span class="field-display-name">{{ fieldDisplayName(scope.row) }}</span>
                    <span v-if="scope.row.display_name && scope.row.display_name !== scope.row.field_name" class="field-technical-name">
                      {{ scope.row.field_name }}
                    </span>
                    <span v-if="fieldValueMappings(scope.row).length" class="field-value-count">
                      {{ t('data_dictionary.field_value_count', { count: fieldValueMappings(scope.row).length }) }}
                    </span>
                  </div>
                </template>
              </el-table-column>
              <el-table-column :label="t('data_dictionary.field_source')" width="112" align="center">
                <template #default="scope">
                  <el-tag
                    size="small"
                    :type="fieldSourceTagType(scope.row)"
                    effect="plain"
                  >
                    {{ fieldSourceLabel(scope.row) }}
                  </el-tag>
                </template>
              </el-table-column>
              <el-table-column :label="t('datasource.field_type')" width="160" show-overflow-tooltip>
                <template #default="scope">
                  {{ fieldTypeLabel(scope.row) }}
                </template>
              </el-table-column>
              <el-table-column :label="t('data_dictionary.source_field')" width="150" show-overflow-tooltip>
                <template #default="scope">
                  {{ scope.row.source_field || '-' }}
                </template>
              </el-table-column>
              <el-table-column :label="t('data_dictionary.json_path')" width="170" show-overflow-tooltip>
                <template #default="scope">
                  {{ scope.row.json_path || '-' }}
                </template>
              </el-table-column>
              <el-table-column :label="t('data_dictionary.field_expression')" min-width="260" show-overflow-tooltip>
                <template #default="scope">
                  <span class="field-expression">{{ scope.row.expression || scope.row.json_path || '-' }}</span>
                </template>
              </el-table-column>
              <el-table-column prop="field_comment" :label="t('datasource.field_original_notes')" min-width="220" show-overflow-tooltip />
              <el-table-column prop="custom_comment" :label="t('datasource.field_notes_1')" min-width="220" show-overflow-tooltip>
                <template #default="scope">
                  {{ scope.row.custom_comment || '-' }}
                </template>
              </el-table-column>
              <template #empty>
                <EmptyBackground :description="t('data_dictionary.empty_field')" img-type="tree" />
              </template>
            </el-table>
          </section>

        </template>

        <div v-else class="detail-empty">
          <el-button :icon="Refresh" :loading="datasourceLoading || schemaLoading" @click="loadDatasources">
            {{ t('common.refresh') }}
          </el-button>
        </div>
      </main>

    <el-drawer
      v-model="dictionaryFieldDrawerVisible"
      :title="dictionaryMode === 'create' ? t('data_dictionary.create_dictionary_field') : t('data_dictionary.alter_dictionary_field')"
      size="620px"
      destroy-on-close
    >
      <el-form
        ref="dictionaryFormRef"
        :model="dictionaryForm"
        :rules="dictionaryFormRules"
        label-position="top"
        class="schema-change-form"
        @submit.prevent
      >
        <el-alert
          :title="t('data_dictionary.dictionary_field_notice')"
          type="info"
          show-icon
          :closable="false"
        />
        <div class="field-editor-grid">
          <el-form-item prop="table_name" :label="t('data_dictionary.table_name')">
            <el-input v-model="dictionaryForm.table_name" :disabled="true" />
          </el-form-item>
          <el-form-item prop="field_name" :label="t('datasource.field_name')">
            <el-input
              v-model="dictionaryForm.field_name"
              :disabled="dictionaryMode === 'edit'"
              :placeholder="t('data_dictionary.dictionary_field_name_placeholder')"
              @blur="syncJsonSourceFromFieldName"
            />
          </el-form-item>
        </div>
        <div class="field-editor-grid">
          <el-form-item :label="t('data_dictionary.source_field')">
            <el-select
              v-model="dictionaryForm.source_field"
              allow-create
              default-first-option
              filterable
              clearable
              :reserve-keyword="false"
              :placeholder="t('data_dictionary.source_field_placeholder')"
              style="width: 100%"
            >
              <el-option
                v-for="option in physicalFieldOptions"
                :key="option.value"
                :label="option.type ? `${option.label} (${option.type})` : option.label"
                :value="option.value"
              />
            </el-select>
          </el-form-item>
          <el-form-item :label="t('data_dictionary.json_path')">
            <el-input
              v-model="dictionaryForm.json_path"
              :placeholder="t('data_dictionary.json_path_placeholder')"
            />
          </el-form-item>
        </div>
        <div class="field-editor-grid">
          <el-form-item :label="t('data_dictionary.field_role')">
            <el-select
              v-model="dictionaryForm.field_role"
              allow-create
              default-first-option
              filterable
              clearable
              :reserve-keyword="false"
              style="width: 100%"
            >
              <el-option
                v-for="option in dictionaryRoleOptions"
                :key="option.value"
                :label="option.label"
                :value="option.value"
              />
            </el-select>
          </el-form-item>
          <el-form-item :label="t('data_dictionary.semantic_type')">
            <el-select
              v-model="dictionaryForm.semantic_type"
              allow-create
              default-first-option
              filterable
              clearable
              :reserve-keyword="false"
              style="width: 100%"
            >
              <el-option
                v-for="option in semanticTypeOptions"
                :key="option.value"
                :label="option.label"
                :value="option.value"
              />
            </el-select>
          </el-form-item>
        </div>
        <el-form-item :label="t('data_dictionary.display_aliases')">
          <el-input
            v-model="dictionaryForm.aliases_text"
            class="schema-textarea schema-textarea--small"
            type="textarea"
            :rows="3"
            :placeholder="t('data_dictionary.display_aliases_placeholder')"
          />
        </el-form-item>
        <el-form-item :label="t('data_dictionary.field_expression')">
          <el-input
            v-model="dictionaryForm.expression"
            class="schema-textarea schema-textarea--medium code-textarea"
            type="textarea"
            :rows="4"
            :placeholder="t('data_dictionary.field_expression_placeholder')"
          />
        </el-form-item>
        <el-form-item :label="t('datasource.field_notes')">
          <el-input
            v-model="dictionaryForm.field_comment"
            class="schema-textarea schema-textarea--medium"
            type="textarea"
            :rows="4"
          />
        </el-form-item>
        <el-form-item :label="t('data_dictionary.ai_notes')">
          <el-input
            v-model="dictionaryForm.ai_notes"
            class="schema-textarea schema-textarea--medium"
            type="textarea"
            :rows="4"
          />
        </el-form-item>
        <el-form-item :label="t('data_dictionary.example_values')">
          <el-input
            v-model="dictionaryForm.example_values_text"
            class="schema-textarea schema-textarea--small"
            type="textarea"
            :rows="3"
            :placeholder="t('data_dictionary.example_values_placeholder')"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <div class="drawer-footer">
          <el-button @click="dictionaryFieldDrawerVisible = false">{{ t('common.cancel') }}</el-button>
          <el-button type="primary" :loading="dictionarySubmitting" @click="submitDictionaryField">
            {{ t('common.save') }}
          </el-button>
        </div>
      </template>
    </el-drawer>

    <el-drawer
      v-model="changeDrawerVisible"
      :title="changeDrawerTitle"
      size="620px"
      destroy-on-close
    >
      <el-form
        ref="changeFormRef"
        :model="changeForm"
        :rules="changeFormRules"
        label-position="top"
        class="schema-change-form"
        @submit.prevent
      >
        <el-alert
          :title="t('data_dictionary.schema_change_readonly_notice')"
          type="info"
          show-icon
          :closable="false"
        />
        <el-form-item prop="table_name" :label="t('data_dictionary.table_name')">
          <el-input
            v-model="changeForm.table_name"
            :disabled="changeForm.change_type === 'alter_table'"
            :placeholder="t('data_dictionary.table_name_placeholder')"
          />
        </el-form-item>
        <el-form-item :label="t('datasource.table_notes')">
          <el-input
            v-model="changeForm.table_comment"
            class="schema-textarea schema-textarea--medium"
            type="textarea"
            :rows="4"
          />
        </el-form-item>
        <el-form-item :label="t('data_dictionary.request_comment')">
          <el-input
            v-model="changeForm.request_comment"
            class="schema-textarea schema-textarea--medium"
            type="textarea"
            :rows="4"
          />
        </el-form-item>

        <div class="field-editor-head">
          <span>{{ t('data_dictionary.fields') }}</span>
          <el-button v-if="changeForm.change_type === 'create_table'" :icon="Plus" @click="addChangeField">
            {{ t('data_dictionary.add_field') }}
          </el-button>
        </div>
        <div class="field-editor-list">
          <div
            v-for="(field, index) in changeForm.fields"
            :key="index"
            class="field-editor-card"
          >
            <div v-if="changeForm.change_type === 'create_table'" class="field-editor-card-head">
              <span>{{ t('data_dictionary.field_item_title', { index: index + 1 }) }}</span>
              <el-button
                text
                :icon="Delete"
                :disabled="changeForm.fields.length <= 1"
                @click="removeChangeField(index)"
              />
            </div>
            <div class="field-editor-grid">
              <el-form-item class="field-editor-item" :label="t('datasource.field_name')">
                <el-input v-model="field.field_name" :placeholder="t('datasource.field_name')" />
              </el-form-item>
              <el-form-item class="field-editor-item" :label="t('datasource.field_type')">
                <el-select
                  v-model="field.field_type"
                  allow-create
                  default-first-option
                  filterable
                  :reserve-keyword="false"
                  :placeholder="t('datasource.field_type')"
                  style="width: 100%"
                >
                  <el-option
                    v-for="option in fieldTypeOptions"
                    :key="option.value"
                    :label="option.label"
                    :value="option.value"
                  />
                </el-select>
              </el-form-item>
            </div>
            <el-form-item class="field-editor-item field-editor-comment" :label="t('datasource.field_notes')">
              <el-input
                v-model="field.field_comment"
                class="schema-textarea schema-textarea--large"
                type="textarea"
                :rows="8"
                resize="vertical"
                :placeholder="t('datasource.field_notes')"
              />
            </el-form-item>
          </div>
        </div>
      </el-form>
      <template #footer>
        <div class="drawer-footer">
          <el-button @click="changeDrawerVisible = false">{{ t('common.cancel') }}</el-button>
          <el-button type="primary" :loading="changeSubmitting" @click="submitSchemaChange">
            {{ t('common.save') }}
          </el-button>
        </div>
      </template>
    </el-drawer>
  </div>
</template>

<style lang="less" scoped>
.data-dictionary-container {
  width: calc(100% + 48px);
  height: calc(100% + 36px);
  min-height: 0;
  margin: -18px -24px;
  display: grid;
  grid-template-columns: 304px minmax(0, 1fr);
  overflow: hidden;
  background: transparent;
  color: var(--workspace-text-primary, #1b2a41);
}

.dictionary-sidebar {
  min-width: 0;
  min-height: 0;
  padding: 26px 16px 18px 20px;
  display: flex;
  flex-direction: column;
  border-right: 1px solid var(--workspace-border, #e2eaf4);
  background: var(--workspace-panel-bg, #f7faff);
}

.dictionary-detail {
  min-width: 0;
  min-height: 0;
  padding: 26px 20px 18px 24px;
  display: flex;
  flex-direction: column;
  overflow: auto;
  background: var(--workspace-card-bg, #fff);
}

.panel-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 12px;
  font-weight: 600;
  font-size: 15px;
  line-height: 23px;

  .muted {
    color: var(--workspace-text-secondary, #66758f);
    font-weight: 400;
  }
}

.table-toolbar {
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  gap: 10px;
  align-items: center;
}

.table-toolbar .panel-head {
  grid-column: 1 / -1;
}

.table-search {
  min-width: 0;
}

.table-list {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  margin-top: 12px;
  padding-right: 4px;
}

.table-item {
  width: 100%;
  border: 0;
  border-radius: 8px;
  background: transparent;
  color: inherit;
  cursor: pointer;
  text-align: left;
  transition:
    background-color 0.16s ease,
    color 0.16s ease;

  &:hover {
    background: var(--workspace-control-hover-bg, #edf3ff);
  }

  &.active {
    background: var(--workspace-primary-soft-bg, #eaf1ff);
    color: var(--ed-color-primary, #2f6bff);
  }
}

.detail-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 20px;
  margin-bottom: 16px;
}

.field-toolbar {
  flex: 1;
  min-width: 0;
  display: flex;
  align-items: center;
  gap: 16px;
}

.schema-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  justify-content: flex-end;

  :deep(.ed-upload) {
    display: flex;
  }
}

.table-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-height: 62px;
  padding: 10px 12px;
  margin-bottom: 4px;
}

.table-name,
.table-comment {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.table-name {
  font-weight: 600;
  font-size: 14px;
  line-height: 22px;
}

.table-comment {
  color: var(--workspace-text-secondary, #66758f);
  font-size: 12px;
  line-height: 18px;
}

.field-panel {
  flex: 1 1 auto;
  min-width: 0;
  min-height: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  background: var(--workspace-card-bg, #fff);
}

.field-search {
  width: 286px;
  flex: 0 0 286px;
}

.field-view-select {
  width: 220px;
  flex: 0 0 220px;
}

.field-table {
  flex: 1;
  min-height: 0;
  color: #1f2329;
  font-size: 14px;
  line-height: 20px;
  --ed-table-header-bg-color: #fff;
  --ed-table-row-hover-bg-color: #f7f8fb;
  --ed-table-border-color: #eff0f1;

  :deep(.ed-table__inner-wrapper) {
    &::before {
      background-color: #eff0f1;
    }
  }

  :deep(.ed-table__header-wrapper th.ed-table__cell) {
    height: 48px;
    padding: 0;
    background: #fff;
    color: #1f2329;
    font-size: 13px;
    font-weight: 600;
    line-height: 20px;
  }

  :deep(.ed-table__header-wrapper .cell) {
    display: flex;
    align-items: center;
    min-height: 48px;
    padding: 0 12px;
  }

  :deep(.ed-table__body tr:nth-child(odd) > td.ed-table__cell) {
    background: #fff;
  }

  :deep(.ed-table__body tr:nth-child(even) > td.ed-table__cell) {
    background: #fafbfc;
  }

  :deep(.ed-table__body tr:hover > td.ed-table__cell) {
    background: #f5f6fa;
  }

  :deep(td.ed-table__cell) {
    height: 56px;
    padding: 0;
    border-color: #eff0f1;
  }

  :deep(td.ed-table__cell .cell) {
    display: flex;
    align-items: center;
    min-height: 56px;
    padding: 0 12px;
    color: #1f2329;
    font-size: 14px;
    line-height: 20px;
  }

  :deep(.ed-table__expanded-cell) {
    padding: 0;
    background: #f8fbff;
  }

  :deep(.field-row--no-values .ed-table__expand-icon) {
    visibility: hidden;
    pointer-events: none;
  }
}

.field-name-cell {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.field-display-name,
.field-technical-name {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.field-display-name {
  color: #1f2329;
  font-weight: 500;
}

.field-technical-name {
  color: #8f959e;
  font-size: 12px;
  line-height: 18px;
}

.field-value-count {
  width: fit-content;
  max-width: 100%;
  padding: 1px 6px;
  border: 1px solid #b9d6ff;
  border-radius: 4px;
  color: #2368d1;
  background: #f2f7ff;
  font-size: 12px;
  line-height: 18px;
}

.field-value-panel {
  padding: 14px 0 16px 0;
  border-top: 1px solid #e7edf6;
  border-bottom: 1px solid #e7edf6;
  background: #f8fbff;
}

.field-value-head {
  margin: 0 18px 10px 18px;
  display: flex;
  align-items: center;
  gap: 8px;
  color: #1f2329;
  font-size: 13px;
  font-weight: 600;
  line-height: 20px;
}

.field-value-table {
  width: calc(100% - 36px);
  margin: 0 18px;
  border: 1px solid #e2eaf4;
  border-radius: 6px;
  overflow: hidden;
}

.field-value-empty {
  padding: 14px 18px;
  color: #8f959e;
  font-size: 13px;
  line-height: 20px;
  background: #f8fbff;
}

.field-expression {
  font-family: Consolas, Monaco, 'Courier New', monospace;
  font-size: 12px;
  color: #4f5869;
}

.sidebar-empty,
.detail-empty {
  margin: auto;
}

.detail-empty {
  width: 100%;
  height: 100%;
  display: flex;
  align-items: flex-start;
  justify-content: flex-end;
}

.schema-change-form {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.field-editor-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-top: 4px;
  color: var(--workspace-text-primary, #1b2a41);
  font-size: 14px;
  line-height: 22px;
  font-weight: 600;
}

.field-editor-list {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.field-editor-card {
  padding: 0 0 14px;
  border-bottom: 1px solid var(--workspace-border, #e2eaf4);
}

.field-editor-card:last-child {
  padding-bottom: 0;
  border-bottom: 0;
}

.field-editor-card-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 10px;
  color: var(--workspace-text-secondary, #66758f);
  font-size: 13px;
  line-height: 20px;
  font-weight: 600;
}

.field-editor-grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
  gap: 12px;
}

.field-editor-item {
  margin-bottom: 14px;
}

.field-editor-comment {
  margin-bottom: 0;
}

.schema-textarea {
  :deep(.ed-textarea__inner) {
    line-height: 22px;
  }
}

.schema-textarea--medium {
  :deep(.ed-textarea__inner) {
    min-height: 86px !important;
  }
}

.schema-textarea--small {
  :deep(.ed-textarea__inner) {
    min-height: 66px !important;
  }
}

.schema-textarea--large {
  :deep(.ed-textarea__inner) {
    min-height: 176px !important;
  }
}

.code-textarea {
  :deep(.ed-textarea__inner) {
    font-family: Consolas, Monaco, 'Courier New', monospace;
    font-size: 12px;
  }
}

.drawer-footer {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}

@media (max-width: 980px) {
  .data-dictionary-container {
    width: 100%;
    height: auto;
    margin: 0;
    grid-template-columns: 1fr;
    overflow: visible;
  }

  .dictionary-sidebar,
  .dictionary-detail {
    min-height: auto;
  }

  .detail-head,
  .field-toolbar {
    flex-direction: column;
    align-items: stretch;
  }

  .field-search {
    width: 100%;
    flex-basis: auto;
  }

  .field-editor-grid {
    grid-template-columns: 1fr;
  }
}
</style>
