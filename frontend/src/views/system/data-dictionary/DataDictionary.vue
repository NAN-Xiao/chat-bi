<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { ElMessage } from 'element-plus'
import { Delete, EditPen, Plus, Refresh } from '@element-plus/icons-vue'
import { datasourceApi } from '@/api/datasource'
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
  display_name?: string
  field_comment?: string
  custom_comment?: string
  checked?: boolean
  field_index?: number
  is_virtual?: boolean
  source_field?: string
  json_path?: string
}

type SchemaTable = {
  id: number | string
  table_name: string
  display_name?: string
  table_comment?: string
  custom_comment?: string
  checked?: boolean
  fields: SchemaField[]
}

type SchemaMetadata = DatasourceItem & {
  tables: SchemaTable[]
}

type SchemaTreeEntry = {
  table: SchemaTable
  jsonFields: SchemaField[]
}

type SchemaChangeField = {
  field_name: string
  field_type: string
  field_comment?: string
  required?: boolean
}

const { t } = useI18n()

const datasourceLoading = ref(false)
const schemaLoading = ref(false)
const changeSubmitting = ref(false)
const metadataSubmitting = ref(false)
const tableKeyword = ref('')
const fieldKeyword = ref('')
const datasources = ref<DatasourceItem[]>([])
const schema = ref<SchemaMetadata | null>(null)
const selectedTableId = ref<number | string | null>(null)
const selectedJsonFieldName = ref('')
const changeDrawerVisible = ref(false)
const metadataDrawerVisible = ref(false)
const changeMode = ref<'create_table' | 'create_field' | 'alter_field'>('create_table')
const metadataMode = ref<'table' | 'field'>('table')
const changeFormRef = ref()
const metadataFormRef = ref()
const changeForm = reactive({
  change_type: 'create_table' as 'create_table' | 'alter_table',
  table_name: '',
  table_comment: '',
  request_comment: '',
  source_table_name: '',
  fields: [] as SchemaChangeField[],
})
const metadataForm = reactive({
  table_name: '',
  field_name: '',
  display_name: '',
  comment: '',
})

const changeFormRules = {
  table_name: [{ required: true, message: t('data_dictionary.table_name_required'), trigger: 'blur' }],
}

const metadataFormRules = {
  display_name: [{ max: 255, message: '展示名不能超过 255 个字符', trigger: 'blur' }],
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

const tableDisplayName = (table: SchemaTable) => table.display_name || table.table_name

const fieldDisplayName = (field: SchemaField) => field.display_name || '-'

const fieldNodeDisplayName = (field: SchemaField) => field.display_name || field.field_name

const sourceFieldName = (field: SchemaField) => {
  if (field.source_field) return field.source_field
  return field.field_name.includes('.') ? field.field_name.split('.')[0] : field.field_name
}

const jsonChildFields = (table: SchemaTable, fieldName: string) => {
  return (table.fields || []).filter((field) => {
    return (field.is_virtual || field.field_type === 'json_path') && sourceFieldName(field) === fieldName
  })
}

const looksLikeJsonViewField = (table: SchemaTable, field: SchemaField) => {
  if (field.is_virtual || field.field_type === 'json_path') return false
  const type = String(field.field_type || '').toLowerCase()
  const comment = `${field.field_comment || ''} ${field.custom_comment || ''}`.toLowerCase()
  return (
    jsonChildFields(table, field.field_name).length > 0 ||
    type === 'json' ||
    type === 'jsonb' ||
    comment.includes('json') ||
    comment.includes('常用路径') ||
    comment.includes('json_extract')
  )
}

const jsonViewFields = (table: SchemaTable) => {
  return (table.fields || []).filter((field) => looksLikeJsonViewField(table, field))
}

const matchesTableKeyword = (table: SchemaTable, keyword: string) => {
  if (!keyword) return true
  return [table.table_name, table.display_name, table.table_comment, table.custom_comment].some((value) =>
    String(value || '').toLowerCase().includes(keyword)
  )
}

const matchesFieldKeyword = (field: SchemaField, keyword: string) => {
  if (!keyword) return true
  return [field.field_name, field.display_name, field.field_type, field.field_comment, field.custom_comment].some((value) =>
    String(value || '').toLowerCase().includes(keyword)
  )
}

const schemaTree = computed<SchemaTreeEntry[]>(() => {
  const keyword = tableKeyword.value.trim().toLowerCase()
  const tables = schema.value?.tables || []
  return tables
    .map((table) => {
      const jsonFields = jsonViewFields(table)
      const tableMatched = matchesTableKeyword(table, keyword)
      const matchedJsonFields = keyword
        ? jsonFields.filter((field) => matchesFieldKeyword(field, keyword))
        : jsonFields
      return {
        table,
        jsonFields: tableMatched ? jsonFields : matchedJsonFields,
      }
    })
    .filter((item) => matchesTableKeyword(item.table, keyword) || item.jsonFields.length > 0)
})

const filteredTables = computed(() => schemaTree.value.map((item) => item.table))

const selectedTable = computed(() => {
  return filteredTables.value.find((item) => String(item.id) === String(selectedTableId.value)) || null
})

const selectedJsonField = computed(() => {
  if (!selectedTable.value || !selectedJsonFieldName.value) return null
  return selectedTable.value.fields.find((field) => field.field_name === selectedJsonFieldName.value) || null
})

const filteredFields = computed(() => {
  const keyword = fieldKeyword.value.trim().toLowerCase()
  const table = selectedTable.value
  if (!table) return []
  const fields = table.fields.filter((field) => !field.is_virtual && !looksLikeJsonViewField(table, field))
  return fields.filter((item) => matchesFieldKeyword(item, keyword))
})

const changeDrawerTitle = computed(() =>
  changeMode.value === 'create_table'
    ? t('data_dictionary.create_table')
    : changeMode.value === 'create_field'
      ? t('data_dictionary.create_field')
    : t('data_dictionary.alter_field')
)

const metadataDrawerTitle = computed(() =>
  metadataMode.value === 'table' ? '配置表展示信息' : '配置字段展示信息'
)

const metadataActionLabel = computed(() =>
  selectedJsonField.value ? '配置字段展示' : '配置表展示'
)

const selectFirstVisibleTable = () => {
  selectedTableId.value = filteredTables.value[0]?.id ?? null
  selectedJsonFieldName.value = ''
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
    schema.value = await datasourceApi.schemaMetadata(id)
    selectFirstVisibleTable()
  } finally {
    schemaLoading.value = false
  }
}

const selectTableNode = (table: SchemaTable) => {
  selectedTableId.value = table.id
  selectedJsonFieldName.value = ''
}

const selectJsonNode = (table: SchemaTable, field: SchemaField) => {
  selectedTableId.value = table.id
  selectedJsonFieldName.value = field.field_name
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

const resetChangeForm = () => {
  changeForm.change_type = 'create_table'
  changeForm.table_name = ''
  changeForm.table_comment = ''
  changeForm.request_comment = ''
  changeForm.source_table_name = ''
  changeForm.fields = [emptyField()]
  changeFormRef.value?.clearValidate?.()
}

const openCreateTable = () => {
  resetChangeForm()
  changeMode.value = 'create_table'
  changeDrawerVisible.value = true
}

const openCreateField = () => {
  if (!selectedTable.value) return
  resetChangeForm()
  changeMode.value = 'create_field'
  changeForm.change_type = 'alter_table'
  changeForm.table_name = selectedTable.value.table_name
  changeForm.source_table_name = selectedTable.value.table_name
  changeForm.table_comment = selectedTable.value.custom_comment || selectedTable.value.table_comment || ''
  changeForm.fields = [emptyField()]
  changeDrawerVisible.value = true
}

const openAlterField = (field: SchemaField) => {
  if (!selectedTable.value) return
  resetChangeForm()
  changeMode.value = 'alter_field'
  changeForm.change_type = 'alter_table'
  changeForm.table_name = selectedTable.value.table_name
  changeForm.source_table_name = selectedTable.value.table_name
  changeForm.table_comment = selectedTable.value.custom_comment || selectedTable.value.table_comment || ''
  changeForm.fields = [{
    field_name: field.field_name,
    field_type: field.field_type || 'text',
    field_comment: field.custom_comment || field.field_comment || '',
    required: false,
  }]
  changeDrawerVisible.value = true
}

const fieldTypeText = (field: SchemaField) => {
  if (field.is_virtual || field.field_type === 'json_path') return 'JSON字段'
  return field.field_type || '-'
}

const canAlterField = (field: SchemaField) => {
  const table = selectedTable.value
  return !!table && !field.is_virtual && !looksLikeJsonViewField(table, field)
}

const resetMetadataForm = () => {
  metadataForm.table_name = ''
  metadataForm.field_name = ''
  metadataForm.display_name = ''
  metadataForm.comment = ''
  metadataFormRef.value?.clearValidate?.()
}

const openTableMetadata = () => {
  const table = selectedTable.value
  if (!table) return
  resetMetadataForm()
  metadataMode.value = 'table'
  metadataForm.table_name = table.table_name
  metadataForm.display_name = table.display_name || ''
  metadataForm.comment = table.custom_comment || table.table_comment || ''
  metadataDrawerVisible.value = true
}

const openSelectedMetadata = () => {
  if (selectedJsonField.value) {
    openFieldMetadata(selectedJsonField.value)
    return
  }
  openTableMetadata()
}

const openFieldMetadata = (field: SchemaField) => {
  if (!selectedTable.value) return
  resetMetadataForm()
  metadataMode.value = 'field'
  metadataForm.table_name = selectedTable.value.table_name
  metadataForm.field_name = field.field_name
  metadataForm.display_name = field.display_name || ''
  metadataForm.comment = field.custom_comment || field.field_comment || ''
  metadataDrawerVisible.value = true
}

const submitMetadata = async () => {
  if (!schema.value || !metadataForm.table_name) return
  const valid = await metadataFormRef.value?.validate?.().catch(() => false)
  if (!valid) return
  const currentTableId = selectedTableId.value
  const currentJsonFieldName = selectedJsonFieldName.value
  metadataSubmitting.value = true
  try {
    schema.value = await datasourceApi.updateSchemaMetadata(schema.value.id, {
      table_name: metadataForm.table_name,
      field_name: metadataMode.value === 'field' ? metadataForm.field_name : undefined,
      display_name: metadataForm.display_name.trim(),
      comment: metadataForm.comment.trim(),
    })
    selectedTableId.value = currentTableId
    selectedJsonFieldName.value = currentJsonFieldName
    metadataDrawerVisible.value = false
    ElMessage.success('展示信息已保存')
  } finally {
    metadataSubmitting.value = false
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
            <el-tooltip :content="t('data_dictionary.create_table')" placement="top">
              <el-button class="table-create-button" :icon="Plus" @click="openCreateTable" />
            </el-tooltip>
          </div>

          <div class="table-list">
            <div
              v-for="item in schemaTree"
              :key="item.table.id"
              class="table-tree-group"
            >
              <button
                type="button"
                class="table-item table-node"
                :class="{ active: String(selectedTableId) === String(item.table.id) && !selectedJsonFieldName }"
                @click="selectTableNode(item.table)"
              >
                <span class="table-name">{{ tableDisplayName(item.table) }}</span>
                <span v-if="item.table.display_name" class="table-physical-name">{{ item.table.table_name }}</span>
                <span class="table-comment">{{ item.table.custom_comment || item.table.table_comment || '-' }}</span>
              </button>
              <div v-if="item.jsonFields.length" class="json-node-list">
                <button
                  v-for="field in item.jsonFields"
                  :key="`${item.table.id}:${field.field_name}`"
                  type="button"
                  class="json-node"
                  :class="{
                    active: String(selectedTableId) === String(item.table.id) && selectedJsonFieldName === field.field_name,
                  }"
                  @click="selectJsonNode(item.table, field)"
                >
                  <span class="json-node-main">
                    <span class="json-node-line" />
                    <span class="json-node-label">{{ fieldNodeDisplayName(field) }}</span>
                  </span>
                  <span v-if="field.display_name" class="json-node-physical">{{ field.field_name }}</span>
                </button>
              </div>
            </div>
            <EmptyBackground
              v-if="!schemaTree.length"
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
            </div>
            <div class="schema-actions">
              <el-button :icon="Refresh" :loading="datasourceLoading || schemaLoading" @click="loadDatasources">
                {{ t('common.refresh') }}
              </el-button>
              <el-button
                :icon="EditPen"
                :disabled="!selectedTable"
                @click="openSelectedMetadata"
              >
                {{ metadataActionLabel }}
              </el-button>
              <el-button :icon="Plus" type="primary" :disabled="!selectedTable || !!selectedJsonFieldName" @click="openCreateField">
                {{ t('data_dictionary.create_field') }}
              </el-button>
            </div>
          </div>

          <section class="field-panel">
            <el-table :data="filteredFields" class="field-table" style="width: 100%">
              <el-table-column prop="display_name" label="展示名" min-width="160" show-overflow-tooltip>
                <template #default="scope">
                  {{ fieldDisplayName(scope.row) }}
                </template>
              </el-table-column>
              <el-table-column prop="field_name" :label="t('datasource.field_name')" min-width="180" show-overflow-tooltip />
              <el-table-column prop="field_type" :label="t('datasource.field_type')" width="120" show-overflow-tooltip>
                <template #default="scope">
                  {{ fieldTypeText(scope.row) }}
                </template>
              </el-table-column>
              <el-table-column prop="field_comment" :label="t('datasource.field_original_notes')" min-width="220" show-overflow-tooltip />
              <el-table-column prop="custom_comment" :label="t('datasource.field_notes_1')" min-width="220" show-overflow-tooltip>
                <template #default="scope">
                  {{ scope.row.custom_comment || '-' }}
                </template>
              </el-table-column>
              <el-table-column fixed="right" :label="t('ds.actions')" width="150" align="center" class-name="field-operation-cell">
                <template #default="scope">
                  <el-button
                    class="field-row-action"
                    text
                    type="primary"
                    size="small"
                    :icon="EditPen"
                    @click="openFieldMetadata(scope.row)"
                  >
                    配置
                  </el-button>
                  <el-button
                    v-if="canAlterField(scope.row)"
                    class="field-row-action"
                    text
                    type="primary"
                    size="small"
                    @click="openAlterField(scope.row)"
                  >
                    {{ t('data_dictionary.alter_field_action') }}
                  </el-button>
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

    <el-drawer
      v-model="metadataDrawerVisible"
      :title="metadataDrawerTitle"
      size="520px"
      destroy-on-close
    >
      <el-form
        ref="metadataFormRef"
        :model="metadataForm"
        :rules="metadataFormRules"
        label-position="top"
        class="schema-change-form"
        @submit.prevent
      >
        <el-alert
          title="展示名和备注保存在当前系统库的数据字典元数据中，不会修改业务库表结构。"
          type="info"
          show-icon
          :closable="false"
        />
        <el-form-item label="表名">
          <el-input v-model="metadataForm.table_name" disabled />
        </el-form-item>
        <el-form-item v-if="metadataMode === 'field'" label="字段名">
          <el-input v-model="metadataForm.field_name" disabled />
        </el-form-item>
        <el-form-item prop="display_name" label="展示中文名">
          <el-input
            v-model="metadataForm.display_name"
            clearable
            placeholder="例如：注册日期、客户端版本、事件名称"
          />
        </el-form-item>
        <el-form-item label="备注 / Tips">
          <el-input
            v-model="metadataForm.comment"
            class="schema-textarea schema-textarea--large"
            type="textarea"
            :rows="8"
            resize="vertical"
            placeholder="鼠标悬浮时展示给用户的字段说明"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <div class="drawer-footer">
          <el-button @click="metadataDrawerVisible = false">{{ t('common.cancel') }}</el-button>
          <el-button type="primary" :loading="metadataSubmitting" @click="submitMetadata">
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
  grid-template-columns: minmax(0, 1fr) 44px;
  gap: 10px;
  align-items: center;
}

.table-toolbar .panel-head {
  grid-column: 1 / -1;
}

.table-search {
  min-width: 0;
}

.table-create-button {
  width: 44px;
  height: 36px;
  min-width: 44px;
  padding: 0;
  border-radius: 8px;
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

  :deep(.field-operation-cell .cell) {
    justify-content: center;
    padding: 0 8px;
  }
}

.field-row-action {
  min-width: 64px;
  height: 28px;
  padding: 0 8px;
  font-size: 14px;
  line-height: 20px;
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

.schema-textarea--large {
  :deep(.ed-textarea__inner) {
    min-height: 176px !important;
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
