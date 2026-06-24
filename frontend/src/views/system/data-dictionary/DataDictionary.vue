<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
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
  field_comment?: string
  custom_comment?: string
  checked?: boolean
  field_index?: number
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

const { t } = useI18n()

const datasourceLoading = ref(false)
const schemaLoading = ref(false)
const tableKeyword = ref('')
const fieldKeyword = ref('')
const datasources = ref<DatasourceItem[]>([])
const schema = ref<SchemaMetadata | null>(null)
const selectedTableId = ref<number | string | null>(null)

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

const filteredFields = computed(() => {
  const keyword = fieldKeyword.value.trim().toLowerCase()
  const fields = selectedTable.value?.fields || []
  if (!keyword) return fields
  return fields.filter((item) => {
    return [item.field_name, item.field_type, item.field_comment, item.custom_comment].some((value) =>
      String(value || '').toLowerCase().includes(keyword)
    )
  })
})

const selectFirstVisibleTable = () => {
  selectedTableId.value = filteredTables.value[0]?.id ?? null
}

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
</script>

<template>
  <div class="data-dictionary-container professional-container">
    <div class="tool-left">
      <div class="title-block">
        <span class="page-title">{{ t('data_dictionary.title') }}</span>
        <p class="page-subtitle">{{ t('data_dictionary.subtitle') }}</p>
      </div>
      <div class="toolbar">
        <el-button secondary :loading="datasourceLoading || schemaLoading" @click="loadDatasources">
          {{ t('common.refresh') }}
        </el-button>
      </div>
    </div>

    <section class="dictionary-shell">
      <main v-loading="schemaLoading" class="schema-panel">
        <template v-if="schema">
          <div class="schema-head">
            <div>
              <div class="schema-title">{{ schema.name }}</div>
              <div class="schema-meta">
                <span>{{ schema.type_name || schema.type || '-' }}</span>
                <span>{{ t('data_dictionary.table_count', { count: schema.tables.length }) }}</span>
              </div>
            </div>
            <el-tag type="info" effect="plain">{{ t('data_dictionary.metadata_only') }}</el-tag>
          </div>

          <div class="schema-body">
            <aside class="table-panel">
              <div class="panel-head">
                <span>{{ t('ds.tables') }}</span>
                <span class="muted">{{ filteredTables.length }}</span>
              </div>
              <el-input
                v-model="tableKeyword"
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
            </aside>

            <section class="field-panel">
              <div class="field-head">
                <div>
                  <div class="field-title">{{ selectedTable?.table_name || '-' }}</div>
                  <div class="field-comment">
                    {{ selectedTable?.custom_comment || selectedTable?.table_comment || '-' }}
                  </div>
                </div>
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
              <el-table :data="filteredFields" class="field-table" style="width: 100%">
                <el-table-column prop="field_name" :label="t('datasource.field_name')" min-width="180" show-overflow-tooltip />
                <el-table-column prop="field_type" :label="t('datasource.field_type')" width="180" show-overflow-tooltip />
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
          </div>
        </template>
        <EmptyBackground
          v-else
          class="schema-empty"
          :description="t('data_dictionary.empty_datasource')"
          img-type="noneWhite"
        />
      </main>
    </section>
  </div>
</template>

<style lang="less" scoped>
.data-dictionary-container {
  height: 100%;
  padding: 8px 0 24px;
  color: var(--workspace-text-primary, #1b2a41);

  .tool-left {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: 16px;
    margin-bottom: 16px;
  }

  .page-title {
    font-weight: 600;
    font-size: 22px;
    line-height: 30px;
  }

  .page-subtitle {
    margin: 6px 0 0;
    color: var(--workspace-text-secondary, #66758f);
    font-size: 14px;
    line-height: 22px;
  }
}

.dictionary-shell {
  min-height: 0;
  height: calc(100% - 70px);
}

.schema-panel,
.table-panel,
.field-panel {
  border: 1px solid var(--workspace-border, #e2eaf4);
  border-radius: 8px;
  background: var(--workspace-card-bg, #fff);
  box-shadow: 0 12px 28px rgba(24, 46, 86, 0.06);
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

.table-list {
  min-height: 0;
  overflow-y: auto;
  margin-top: 12px;
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

.schema-panel {
  min-width: 0;
  min-height: 0;
  padding: 18px;
  display: flex;
  flex-direction: column;
}

.schema-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 16px;
}

.schema-title {
  font-weight: 600;
  font-size: 20px;
  line-height: 28px;
}

.schema-meta {
  display: flex;
  align-items: center;
  gap: 14px;
  margin-top: 4px;
  color: var(--workspace-text-secondary, #66758f);
  font-size: 13px;
  line-height: 20px;
}

.schema-body {
  flex: 1;
  min-height: 0;
  display: grid;
  grid-template-columns: 300px minmax(0, 1fr);
  gap: 16px;
}

.table-panel {
  min-width: 0;
  padding: 14px;
  display: flex;
  flex-direction: column;
}

.table-list {
  flex: 1;
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
  min-width: 0;
  min-height: 0;
  padding: 14px;
  display: flex;
  flex-direction: column;
}

.field-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 14px;
}

.field-title {
  font-weight: 600;
  font-size: 17px;
  line-height: 25px;
}

.field-comment {
  margin-top: 4px;
  color: var(--workspace-text-secondary, #66758f);
  font-size: 13px;
  line-height: 20px;
}

.field-search {
  width: 260px;
  flex: 0 0 260px;
}

.field-table {
  flex: 1;
}

.schema-empty {
  margin: auto;
}

@media (max-width: 980px) {
  .dictionary-shell,
  .schema-body {
    grid-template-columns: 1fr;
    height: auto;
  }

  .field-head {
    flex-direction: column;
  }

  .field-search {
    width: 100%;
    flex-basis: auto;
  }
}
</style>
