<script setup lang="ts">
import { computed, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus-secondary'
import { REPORT_TYPES, createDefaultReportConfig, getReportType, type ReportTypeKey } from './reportTypes'

const visible = ref(false)
const selectedType = ref<ReportTypeKey>('event')
const name = ref('')
const config = reactive<any>(createDefaultReportConfig(selectedType.value))
const newFilter = ref('')
const newGroup = ref('')

const definition = computed(() => getReportType(selectedType.value))
const isRetention = computed(() => selectedType.value === 'retention')
const isFunnel = computed(() => selectedType.value === 'funnel')

const resetConfig = (type: ReportTypeKey) => {
  selectedType.value = type
  Object.assign(config, createDefaultReportConfig(type))
  newFilter.value = ''
  newGroup.value = ''
}

const open = (initial?: { type?: ReportTypeKey; name?: string }) => {
  name.value = initial?.name || ''
  resetConfig(initial?.type || 'event')
  visible.value = true
}

const addListItem = (target: 'globalFilters' | 'groupItems', input: string) => {
  const value = input.trim()
  if (!value) return
  config[target].push(value)
  if (target === 'globalFilters') newFilter.value = ''
  else newGroup.value = ''
}

const removeListItem = (target: 'globalFilters' | 'groupItems', item: string) => {
  config[target] = config[target].filter((value: string) => value !== item)
}

const confirm = () => {
  if (!name.value.trim()) {
    ElMessage.warning('请输入报表名称')
    return
  }
  const reportType = getReportType(selectedType.value)
  const reportConfig = JSON.parse(JSON.stringify(config))
  reportConfig.fields = { ...config.fields }
  emit('confirm', {
    name: name.value.trim(),
    reportMeta: {
      type: selectedType.value,
      label: reportType.label,
      config: reportConfig,
    },
  })
  visible.value = false
}

const emit = defineEmits<{
  confirm: [payload: { name: string; reportMeta: Record<string, any> }]
}>()

defineExpose({ open })
</script>

<template>
  <el-dialog
    v-model="visible"
    title="新建报表"
    width="860px"
    class="report-type-dialog"
    append-to-body
    destroy-on-close
  >
    <div class="report-picker">
      <aside class="report-type-nav" aria-label="报表分类">
        <button
          v-for="item in REPORT_TYPES"
          :key="item.key"
          type="button"
          class="report-type-nav-item"
          :class="{ active: selectedType === item.key }"
          @click="resetConfig(item.key)"
        >
          <span class="report-type-dot" :data-type="item.key"></span>
          <span>{{ item.label }}</span>
        </button>
      </aside>

      <section class="report-config" aria-live="polite">
        <header class="report-config-header">
          <div>
            <h3>{{ definition.label }}</h3>
            <p>{{ definition.description }}</p>
          </div>
          <el-input v-model="name" class="report-name" placeholder="报表名称" clearable />
        </header>

        <div class="report-config-body">
          <div class="config-line unit-line">
            <span class="config-icon">◈</span>
            <span>对</span>
            <el-select v-model="config.analysisUnit" class="unit-select" aria-label="分析对象">
              <el-option label="用户" value="用户" />
              <el-option label="设备" value="设备" />
              <el-option label="会话" value="会话" />
            </el-select>
            <span>进行分析</span>
          </div>

          <div v-if="isFunnel" class="step-list">
            <div v-for="(field, index) in definition.fields" :key="field.key" class="step-row">
              <span class="step-index">{{ index + 1 }}</span>
              <el-input v-model="config.fields[field.key]" :placeholder="field.placeholder" />
            </div>
          </div>
          <div v-else class="event-fields">
            <div v-for="field in definition.fields" :key="field.key" class="event-field">
              <label>{{ field.label }}</label>
              <el-input v-model="config.fields[field.key]" :placeholder="field.placeholder" />
            </div>
          </div>

          <div v-if="isRetention" class="switch-stack">
            <label class="switch-row">
              <span>使用间隔展示</span>
              <el-switch v-model="config.useIntervalDisplay" />
            </label>
            <label class="switch-row">
              <span>使用关联属性</span>
              <el-switch v-model="config.useRelatedProperty" />
            </label>
          </div>
          <div v-else class="switch-stack">
            <label class="switch-row">
              <span>使用关联属性</span>
              <el-switch v-model="config.useRelatedProperty" />
            </label>
            <label v-if="isFunnel" class="window-row">
              <span>分析窗口期</span>
              <el-input-number v-model="config.analysisWindowDays" :min="1" :max="365" controls-position="right" />
              <span>天</span>
            </label>
          </div>

          <div class="config-section">
            <div class="section-title"><span>⇵</span><span>全局筛选</span></div>
            <div class="chip-list">
              <span v-for="item in config.globalFilters" :key="item" class="config-chip">
                {{ item }}
                <button type="button" aria-label="移除筛选" @click="removeListItem('globalFilters', item)">×</button>
              </span>
              <el-input
                v-model="newFilter"
                class="inline-add-input"
                placeholder="添加筛选条件"
                @keyup.enter="addListItem('globalFilters', newFilter)"
              />
            </div>
          </div>
          <div class="config-section">
            <div class="section-title"><span>⁙</span><span>分组项</span></div>
            <div class="chip-list">
              <span v-for="item in config.groupItems" :key="item" class="config-chip">
                {{ item }}
                <button type="button" aria-label="移除分组项" @click="removeListItem('groupItems', item)">×</button>
              </span>
              <el-input
                v-model="newGroup"
                class="inline-add-input"
                placeholder="添加分组项"
                @keyup.enter="addListItem('groupItems', newGroup)"
              />
            </div>
          </div>
        </div>
      </section>
    </div>
    <template #footer>
      <el-button @click="visible = false">取消</el-button>
      <el-button type="primary" @click="confirm">创建报表</el-button>
    </template>
  </el-dialog>
</template>

<style scoped lang="less">
.report-picker {
  display: flex;
  min-height: 480px;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  overflow: hidden;
  background: #fff;
}

.report-type-nav {
  flex: 0 0 180px;
  padding: 12px 8px;
  border-right: 1px solid #edf0f3;
  background: #fafbfc;
}

.report-type-nav-item {
  display: flex;
  align-items: center;
  width: 100%;
  min-height: 38px;
  gap: 10px;
  padding: 0 12px;
  border: 0;
  border-radius: 6px;
  color: #4e5969;
  background: transparent;
  cursor: pointer;
  font-size: 13px;
  text-align: left;
}

.report-type-nav-item:hover { background: #eef3ff; }
.report-type-nav-item.active { color: #2f6bff; background: #eaf0ff; font-weight: 600; }
.report-type-dot { width: 8px; height: 8px; border-radius: 2px; background: #2f6bff; }
.report-type-dot[data-type='retention'], .report-type-dot[data-type='funnel'], .report-type-dot[data-type='revenue'] { background: #ff7043; }
.report-type-dot[data-type='heatmap'], .report-type-dot[data-type='distribution'] { background: #20b486; }
.report-type-dot[data-type='ranking'], .report-type-dot[data-type='attribution'] { background: #7c5cff; }

.report-config { flex: 1; min-width: 0; padding: 22px 28px 16px; }
.report-config-header { display: flex; align-items: flex-start; justify-content: space-between; gap: 20px; padding-bottom: 18px; border-bottom: 1px solid #edf0f3; }
.report-config-header h3 { margin: 0 0 6px; color: #1f2329; font-size: 18px; font-weight: 600; }
.report-config-header p { margin: 0; color: #86909c; font-size: 12px; }
.report-name { flex: 0 0 180px; }
.report-config-body { padding-top: 20px; color: #303640; font-size: 13px; }
.config-line, .switch-row, .window-row, .section-title { display: flex; align-items: center; gap: 8px; }
.unit-line { margin-bottom: 20px; font-size: 15px; }
.config-icon { color: #4e5969; font-size: 16px; }
.unit-select { width: 88px; }
.event-fields { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 14px; }
.event-field label { display: block; margin-bottom: 7px; color: #86909c; font-size: 12px; }
.step-list { display: grid; gap: 10px; }
.step-row { display: flex; align-items: center; gap: 10px; }
.step-index { display: inline-flex; align-items: center; justify-content: center; width: 24px; height: 24px; border-radius: 7px; color: #fff; background: #252b56; font-size: 12px; }
.step-row .el-input { flex: 1; }
.switch-stack { display: grid; gap: 12px; margin-top: 18px; }
.switch-row { justify-content: space-between; max-width: 300px; color: #606a78; }
.window-row { color: #606a78; }
.window-row .el-input-number { width: 96px; }
.config-section { margin-top: 24px; padding-top: 15px; border-top: 1px solid #f0f2f5; }
.section-title { margin-bottom: 10px; color: #a1a7b0; font-size: 14px; }
.chip-list { display: flex; align-items: center; flex-wrap: wrap; gap: 8px; min-height: 32px; }
.config-chip { display: inline-flex; align-items: center; gap: 4px; padding: 5px 8px; border-radius: 5px; color: #4e5969; background: #f2f4f7; }
.config-chip button { padding: 0; border: 0; color: #86909c; background: transparent; cursor: pointer; }
.inline-add-input { width: 150px; }

:deep(.report-type-dialog .el-dialog__body) { padding-top: 8px; }
@media (max-width: 720px) {
  .report-picker { min-height: 0; flex-direction: column; }
  .report-type-nav { flex-basis: auto; display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); border-right: 0; border-bottom: 1px solid #edf0f3; }
  .report-config { padding: 18px 16px 12px; }
  .report-config-header { display: block; }
  .report-name { width: 100%; margin-top: 14px; }
  .event-fields { grid-template-columns: 1fr; }
}
</style>
