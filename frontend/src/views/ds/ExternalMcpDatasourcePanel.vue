<script lang="ts" setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus-secondary'
import icon_add_outlined from '@/assets/svg/icon_add_outlined.svg'
import icon_searchOutline_outlined from '@/assets/svg/icon_search-outline_outlined.svg'
import IconOpeEdit from '@/assets/svg/icon_edit_outlined.svg'
import EmptyBackground from '@/views/dashboard/common/EmptyBackground.vue'
import { externalMcpApi, type ExternalMcpServerInfo } from '@/api/externalMcp'
import { formatTimestamp } from '@/utils/date'
import { useI18n } from 'vue-i18n'

const { t } = useI18n()

const keyword = ref('')
const loading = ref(false)
const saving = ref(false)
const drawerVisible = ref(false)
const rows = ref<ExternalMcpServerInfo[]>([])
const formRef = ref()

const defaultForm = {
  id: '' as number | string,
  name: '',
  endpoint: '',
  description: '',
  auth_type: 'bearer',
  auth_header_name: 'Authorization',
  auth_token: '',
  server_name: '',
  server_version: '',
  status: 1,
}

const form = reactive({ ...defaultForm })
const isEdit = computed(() => Boolean(form.id))

const rules = computed(() => ({
  name: [{ required: true, message: t('datasource.external_mcp_name_required'), trigger: 'blur' }],
  endpoint: [
    { required: true, message: t('datasource.external_mcp_endpoint_required'), trigger: 'blur' },
  ],
  auth_header_name: [
    {
      required: true,
      message: t('datasource.external_mcp_auth_header_required'),
      trigger: 'blur',
    },
  ],
}))

const filteredRows = computed(() => {
  const value = keyword.value.trim().toLowerCase()
  if (!value) return rows.value
  return rows.value.filter((row) =>
    [row.name, row.endpoint, row.server_name, row.server_version, row.description].some((item) =>
      String(item || '')
        .toLowerCase()
        .includes(value)
    )
  )
})

const loadRows = async () => {
  loading.value = true
  try {
    rows.value = await externalMcpApi.list({ include_disabled: true })
  } finally {
    loading.value = false
  }
}

const resetForm = () => {
  Object.assign(form, defaultForm)
  formRef.value?.clearValidate?.()
}

const openAdd = () => {
  resetForm()
  drawerVisible.value = true
}

const openEdit = (row: ExternalMcpServerInfo) => {
  Object.assign(form, {
    id: row.id,
    name: row.name || '',
    endpoint: row.endpoint || '',
    description: row.description || '',
    auth_type: row.auth_type || 'bearer',
    auth_header_name: row.auth_header_name || 'Authorization',
    auth_token: '',
    server_name: row.server_name || '',
    server_version: row.server_version || '',
    status: Number(row.status) === 1 ? 1 : 0,
  })
  formRef.value?.clearValidate?.()
  drawerVisible.value = true
}

const closeDrawer = () => {
  drawerVisible.value = false
  resetForm()
}

const buildPayload = () => {
  const payload: Record<string, any> = {
    name: form.name.trim(),
    endpoint: form.endpoint.trim(),
    description: form.description.trim() || null,
    auth_type: form.auth_type || 'bearer',
    auth_header_name: form.auth_header_name.trim() || 'Authorization',
    server_name: form.server_name.trim() || null,
    server_version: form.server_version.trim() || null,
    status: Number(form.status) === 1 ? 1 : 0,
  }
  if (isEdit.value) payload.id = form.id
  if (form.auth_token.trim()) payload.auth_token = form.auth_token.trim()
  return payload
}

const save = () => {
  formRef.value?.validate(async (valid: boolean) => {
    if (!valid) return
    saving.value = true
    try {
      const payload = buildPayload()
      if (isEdit.value) {
        await externalMcpApi.edit(payload)
      } else {
        await externalMcpApi.add(payload)
      }
      ElMessage.success(t('common.save_success'))
      closeDrawer()
      await loadRows()
    } finally {
      saving.value = false
    }
  })
}

const toggleStatus = async (row: ExternalMcpServerInfo, nextStatus: number) => {
  saving.value = true
  try {
    await externalMcpApi.edit({
      id: row.id,
      name: row.name,
      endpoint: row.endpoint,
      description: row.description || null,
      auth_type: row.auth_type || 'bearer',
      auth_header_name: row.auth_header_name || 'Authorization',
      server_name: row.server_name || null,
      server_version: row.server_version || null,
      status: nextStatus,
    })
    ElMessage.success(t('common.save_success'))
    await loadRows()
  } finally {
    saving.value = false
  }
}

const formatOptionalTimestamp = (value?: number | string | null) => {
  const timestamp = Number(value || 0)
  return timestamp ? formatTimestamp(timestamp, 'YYYY-MM-DD HH:mm:ss') : '-'
}

onMounted(loadRows)
</script>

<template>
  <div class="external-mcp-panel">
    <div class="external-mcp-toolbar">
      <el-input
        v-model="keyword"
        clearable
        class="external-mcp-search"
        :placeholder="t('datasource.external_mcp_search')"
      >
        <template #prefix>
          <el-icon>
            <icon_searchOutline_outlined class="svg-icon" />
          </el-icon>
        </template>
      </el-input>
      <el-button type="primary" @click="openAdd">
        <template #icon>
          <icon_add_outlined></icon_add_outlined>
        </template>
        {{ t('datasource.new_external_mcp') }}
      </el-button>
    </div>

    <el-table
      v-loading="loading"
      :data="filteredRows"
      row-key="id"
      class="external-mcp-table"
      height="100%"
    >
      <el-table-column prop="name" :label="t('datasource.external_mcp_name')" min-width="180">
        <template #default="scope">
          <div class="mcp-name-cell">
            <span class="mcp-name ellipsis" :title="scope.row.name">{{ scope.row.name }}</span>
            <span class="mcp-meta ellipsis" :title="scope.row.description || ''">
              {{ scope.row.description || '-' }}
            </span>
          </div>
        </template>
      </el-table-column>
      <el-table-column prop="endpoint" label="Endpoint" min-width="280">
        <template #default="scope">
          <span class="ellipsis" :title="scope.row.endpoint">{{ scope.row.endpoint }}</span>
        </template>
      </el-table-column>
      <el-table-column :label="t('datasource.external_mcp_auth')" width="170">
        <template #default="scope">
          <div class="mcp-name-cell">
            <span>{{ scope.row.auth_type || 'bearer' }}</span>
            <span class="mcp-meta">{{ scope.row.auth_header_name || 'Authorization' }}</span>
          </div>
        </template>
      </el-table-column>
      <el-table-column :label="t('datasource.external_mcp_credential')" width="130">
        <template #default="scope">
          <el-tag :type="scope.row.credential_configured ? 'success' : 'info'" effect="light">
            {{
              scope.row.credential_configured
                ? t('datasource.external_mcp_credential_set')
                : t('datasource.external_mcp_credential_empty')
            }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column :label="t('datasource.external_mcp_server')" min-width="170">
        <template #default="scope">
          <span class="ellipsis">
            {{ [scope.row.server_name, scope.row.server_version].filter(Boolean).join(' / ') || '-' }}
          </span>
        </template>
      </el-table-column>
      <el-table-column :label="t('tenant.status')" width="120">
        <template #default="scope">
          <el-switch
            :model-value="Number(scope.row.status) === 1"
            :loading="saving"
            @change="(value: boolean) => toggleStatus(scope.row, value ? 1 : 0)"
          />
        </template>
      </el-table-column>
      <el-table-column prop="update_time" :label="t('tenant.update_time')" width="180">
        <template #default="scope">
          {{ formatOptionalTimestamp(scope.row.update_time) }}
        </template>
      </el-table-column>
      <el-table-column fixed="right" :label="t('ds.actions')" width="96">
        <template #default="scope">
          <el-tooltip :content="t('datasource.edit')" placement="top">
            <el-icon class="mcp-action-btn" size="16" @click="openEdit(scope.row)">
              <IconOpeEdit />
            </el-icon>
          </el-tooltip>
        </template>
      </el-table-column>
      <template #empty>
        <EmptyBackground :description="t('datasource.external_mcp_empty')" img-type="tree" />
      </template>
    </el-table>

    <el-drawer
      v-model="drawerVisible"
      :title="isEdit ? t('datasource.edit_external_mcp') : t('datasource.new_external_mcp')"
      destroy-on-close
      size="520px"
      :before-close="closeDrawer"
    >
      <el-form
        ref="formRef"
        :model="form"
        :rules="rules"
        label-position="top"
        class="external-mcp-form form-content_error"
        @submit.prevent
      >
        <el-form-item prop="name" :label="t('datasource.external_mcp_name')">
          <el-input v-model="form.name" maxlength="128" clearable />
        </el-form-item>
        <el-form-item prop="endpoint" label="Endpoint">
          <el-input
            v-model="form.endpoint"
            maxlength="1000"
            clearable
            placeholder="https://example.com/mcp"
          />
        </el-form-item>
        <el-form-item :label="t('ds.form.description')">
          <el-input v-model="form.description" type="textarea" :rows="3" maxlength="1000" />
        </el-form-item>
        <el-form-item :label="t('datasource.external_mcp_auth_type')">
          <el-select v-model="form.auth_type" style="width: 100%">
            <el-option label="Bearer" value="bearer" />
          </el-select>
        </el-form-item>
        <el-form-item prop="auth_header_name" :label="t('datasource.external_mcp_auth_header')">
          <el-input v-model="form.auth_header_name" maxlength="128" clearable />
        </el-form-item>
        <el-form-item :label="t('datasource.external_mcp_auth_token')">
          <el-input
            v-model="form.auth_token"
            type="password"
            show-password
            maxlength="4000"
            autocomplete="new-password"
            :placeholder="
              isEdit
                ? t('datasource.external_mcp_token_keep_placeholder')
                : t('datasource.external_mcp_token_placeholder')
            "
          />
        </el-form-item>
        <el-form-item :label="t('datasource.external_mcp_server_name')">
          <el-input v-model="form.server_name" maxlength="128" clearable />
        </el-form-item>
        <el-form-item :label="t('datasource.external_mcp_server_version')">
          <el-input v-model="form.server_version" maxlength="64" clearable />
        </el-form-item>
        <el-form-item :label="t('tenant.status')">
          <el-switch
            v-model="form.status"
            :active-value="1"
            :inactive-value="0"
            :active-text="t('tenant.enabled')"
            :inactive-text="t('tenant.disabled')"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <div class="external-mcp-footer">
          <el-button secondary @click="closeDrawer">{{ t('common.cancel') }}</el-button>
          <el-button type="primary" :loading="saving" @click="save">
            {{ t('common.save') }}
          </el-button>
        </div>
      </template>
    </el-drawer>
  </div>
</template>

<style lang="less" scoped>
.external-mcp-panel {
  height: calc(100% - 56px);
  display: flex;
  flex-direction: column;
  padding: 0 24px 16px;
  min-height: 0;
}

.external-mcp-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 12px;
  flex: 0 0 auto;
}

.external-mcp-search {
  width: 320px;
}

.external-mcp-table {
  flex: 1 1 auto;
  min-height: 0;
}

.mcp-name-cell {
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.mcp-name {
  font-weight: 500;
  color: #1f2329;
}

.mcp-meta {
  font-size: 12px;
  line-height: 20px;
  color: #8f959e;
}

.mcp-action-btn {
  color: #646a73;
  cursor: pointer;
}

.mcp-action-btn:hover {
  color: var(--ed-color-primary);
}

.external-mcp-form {
  padding-right: 4px;
}

.external-mcp-footer {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
}
</style>
