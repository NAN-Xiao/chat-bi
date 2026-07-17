<script setup lang="ts">
import { ref, watch } from 'vue'
import { ElMessage } from 'element-plus-secondary'
import { roiCustomErrorRequestConfig, roiDashboardApi } from '@/api/roiDashboard'
import type { RoiConfig, RoiDatasourceOption } from './types'
import {
  createRoiDatasourceDialogCloseGuard,
  getRoiDatasourceSaveErrorMessage,
} from './roiDatasourceDialogBehavior'

const props = defineProps<{
  modelValue: boolean
  config: RoiConfig | null
}>()

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  saved: [config: RoiConfig]
  cancelled: []
}>()

const options = ref<RoiDatasourceOption[]>([])
const datasourceId = ref<number | null>(null)
const loading = ref(false)
const saving = ref(false)
const closeGuard = createRoiDatasourceDialogCloseGuard()
let activeSaveToken: ReturnType<typeof closeGuard.beginSave> = null

async function loadOptions() {
  loading.value = true
  try {
    options.value = await roiDashboardApi.listDatasources(roiCustomErrorRequestConfig)
  } catch {
    options.value = []
    ElMessage.error('加载 ROI 数据源失败，请稍后重试')
  } finally {
    loading.value = false
  }
}

watch(
  () => props.modelValue,
  (visible) => {
    if (!visible) return
    closeGuard.beginOpen()
    activeSaveToken = null
    saving.value = false
    datasourceId.value = props.config?.datasource_id ?? null
    void loadOptions()
  },
  { immediate: true }
)

async function save() {
  if (datasourceId.value === null) {
    ElMessage.warning('请选择数据源')
    return
  }
  const saveToken = closeGuard.beginSave()
  if (!saveToken) return
  activeSaveToken = saveToken
  saving.value = true
  try {
    const config = await roiDashboardApi.updateConfig(
      {
        datasource_id: datasourceId.value,
        version: props.config?.version ?? null,
      },
      roiCustomErrorRequestConfig
    )
    if (!closeGuard.markSaved(saveToken)) return
    emit('saved', config)
    emit('update:modelValue', false)
  } catch (error) {
    if (closeGuard.isCurrent(saveToken)) {
      ElMessage.error(getRoiDatasourceSaveErrorMessage(error))
    }
  } finally {
    if (activeSaveToken === saveToken) {
      activeSaveToken = null
      saving.value = false
    }
  }
}

function cancel() {
  if (!closeGuard.beginCancel()) return
  activeSaveToken = null
  saving.value = false
  emit('cancelled')
  emit('update:modelValue', false)
}
</script>

<template>
  <el-dialog
    :model-value="modelValue"
    title="设置数据源"
    width="480px"
    append-to-body
    destroy-on-close
    :close-on-click-modal="false"
    @close="cancel"
  >
    <el-form label-position="top">
      <el-form-item label="数据源" required>
        <el-select
          v-model="datasourceId"
          class="roi-datasource-select"
          placeholder="请选择数据源"
          filterable
          :loading="loading"
        >
          <el-option
            v-for="item in options"
            :key="item.id"
            :label="item.name"
            :value="item.id"
          >
            <span>{{ item.name }}</span>
            <span class="datasource-type">{{ item.type_name || item.type }}</span>
          </el-option>
        </el-select>
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="cancel">取消</el-button>
      <el-button type="primary" :loading="saving" @click="save">保存</el-button>
    </template>
  </el-dialog>
</template>

<style scoped lang="less">
.roi-datasource-select {
  width: 100%;
}

.datasource-type {
  float: right;
  margin-left: 16px;
  color: var(--ed-text-color-secondary);
  font-size: 12px;
}
</style>
