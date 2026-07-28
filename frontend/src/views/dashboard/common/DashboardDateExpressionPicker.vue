<script setup lang="ts">
import { computed, ref } from 'vue'
import { ElConfigProvider, ElDatePickerPanel } from 'element-plus'
import 'element-plus/es/components/date-picker-panel/style/css'
import elementZhCnLocale from 'element-plus/es/locale/lang/zh-cn'
import {
  DASHBOARD_DATE_PRESETS,
  DASHBOARD_DATE_PRESET_LABELS,
  cloneDashboardDateExpression,
  formatDashboardDateExpression,
  resolveDashboardDateExpression,
  validateDashboardDateExpression,
  type DashboardDateEndpoint,
  type DashboardDateExpression,
  type DashboardDatePreset,
} from './dashboardDateExpression'

const props = withDefaults(
  defineProps<{
    disabled?: boolean
    timezone?: string
  }>(),
  {
    disabled: false,
    timezone: 'Asia/Shanghai',
  }
)

const model = defineModel<DashboardDateExpression | null>({ default: null })
const emit = defineEmits<{
  apply: [value: DashboardDateExpression]
  cancel: []
}>()

const defaultExpression: DashboardDateExpression = {
  version: 1,
  mode: 'preset',
  preset: 'past_30_days',
}
const visible = ref(false)
const appliedWhileOpen = ref(false)
const draft = ref<DashboardDateExpression>(cloneDashboardDateExpression(defaultExpression))
const now = ref(new Date())

const preview = computed(() =>
  resolveDashboardDateExpression(draft.value, now.value, props.timezone)
)
const validation = computed(() =>
  validateDashboardDateExpression(draft.value, now.value, props.timezone)
)
const buttonLabel = computed(() =>
  model.value ? formatDashboardDateExpression(model.value) : '选择时间'
)
const activePreset = computed(() => (draft.value.mode === 'preset' ? draft.value.preset : ''))
type CalendarRange = [string, string] | []

const calendarRange = computed<CalendarRange>({
  get: (): CalendarRange => draft.value.mode === 'preset' && draft.value.preset === 'all_time'
    ? []
    : [preview.value.start, preview.value.end],
  set: updateCalendarRange,
})

function openPicker() {
  if (props.disabled) return
  now.value = new Date()
  appliedWhileOpen.value = false
  draft.value = cloneDashboardDateExpression(model.value || defaultExpression)
}

function closeWithoutApply() {
  visible.value = false
}

function handleHide() {
  if (!appliedWhileOpen.value) emit('cancel')
  appliedWhileOpen.value = false
}

function selectPreset(preset: DashboardDatePreset) {
  draft.value = { version: 1, mode: 'preset', preset }
}

function useCustomRange() {
  const range = preview.value
  draft.value = {
    version: 1,
    mode: 'range',
    start: { mode: 'static', date: range.start },
    end: { mode: 'dynamic', unit: 'day', offset: 0 },
  }
}

function ensureRange() {
  if (draft.value.mode === 'range') return draft.value
  const range: Extract<DashboardDateExpression, { mode: 'range' }> = {
    version: 1,
    mode: 'range',
    start: { mode: 'static', date: preview.value.start },
    end: { mode: 'dynamic', unit: 'day', offset: 0 },
  }
  draft.value = range
  return range
}

function setEndpointMode(side: 'start' | 'end', value: string | number | boolean) {
  const range = ensureRange()
  range[side] = value === 'static'
    ? { mode: 'static', date: preview.value[side] }
    : { mode: 'dynamic', unit: 'day', offset: side === 'start' ? -30 : 0 }
}

function updateEndpoint(side: 'start' | 'end', value: DashboardDateEndpoint) {
  const range = ensureRange()
  range[side] = value
}

function dynamicDays(endpoint: DashboardDateEndpoint) {
  return endpoint.mode === 'dynamic' ? Math.abs(Math.min(0, endpoint.offset)) : 0
}

function updateDynamicDays(side: 'start' | 'end', value: number | undefined) {
  const days = Number.isFinite(value) ? Math.max(0, Math.trunc(value || 0)) : 0
  updateEndpoint(side, { mode: 'dynamic', unit: 'day', offset: -days })
}

function updateCalendarRange(value: CalendarRange | null) {
  if (!Array.isArray(value) || value.length !== 2) return
  const [start, end] = value
  if (!start || !end) return
  draft.value = {
    version: 1,
    mode: 'range',
    start: { mode: 'static', date: start },
    end: { mode: 'static', date: end },
  }
}

function applyDraft() {
  if (!validation.value.valid) return
  const next = cloneDashboardDateExpression(draft.value)
  model.value = next
  appliedWhileOpen.value = true
  visible.value = false
  emit('apply', next)
}
</script>

<template>
  <el-popover
    v-model:visible="visible"
    :width="680"
    placement="bottom-start"
    trigger="click"
    popper-class="dashboard-date-expression-popper"
    @before-enter="openPicker"
    @hide="handleHide"
  >
    <template #reference>
      <el-button class="date-expression-trigger" :disabled="disabled">
        {{ buttonLabel }}
      </el-button>
    </template>

    <div class="date-expression-picker">
      <header class="picker-header">
        <span class="picker-title">日期范围</span>
        <strong>{{ formatDashboardDateExpression(draft) }}</strong>
        <span>{{ preview.start }} → {{ preview.end }}</span>
      </header>

      <div class="picker-body">
        <aside class="preset-options">
          <span class="preset-caption">系统内置</span>
          <div class="preset-grid">
            <button
              v-for="preset in DASHBOARD_DATE_PRESETS"
              :key="preset"
              type="button"
              :class="{ active: activePreset === preset }"
              @click="selectPreset(preset)"
            >
              {{ DASHBOARD_DATE_PRESET_LABELS[preset] }}
            </button>
          </div>
          <button type="button" class="custom-range-button" @click="useCustomRange">
            自定义时间
            <span>›</span>
          </button>
        </aside>

        <main class="range-editor">
          <div v-if="draft.mode === 'range'" class="endpoint-controls">
            <section v-for="side in (['start', 'end'] as const)" :key="side" class="endpoint-panel">
              <span class="endpoint-caption">{{ side === 'start' ? '开始时间' : '结束时间' }}</span>
              <el-segmented
                class="endpoint-mode"
                :model-value="draft[side].mode"
                :options="[
                  { label: '动态时间', value: 'dynamic' },
                  { label: '静态时间', value: 'static' },
                ]"
                @change="setEndpointMode(side, $event)"
              />
              <div v-if="draft[side].mode === 'dynamic'" class="dynamic-input">
                <el-input-number
                  :model-value="dynamicDays(draft[side])"
                  :min="0"
                  :max="36500"
                  controls-position="right"
                  @change="updateDynamicDays(side, $event)"
                />
                <span>天前</span>
              </div>
              <el-date-picker
                v-else
                :model-value="draft[side].date"
                type="date"
                value-format="YYYY-MM-DD"
                :clearable="false"
                @update:model-value="updateEndpoint(side, { mode: 'static', date: String($event) })"
              />
              <span class="endpoint-result">{{ preview[side] }}</span>
            </section>
          </div>
          <div class="calendar-panel">
            <ElConfigProvider :locale="elementZhCnLocale">
              <ElDatePickerPanel
                v-model="calendarRange"
                type="daterange"
                value-format="YYYY-MM-DD"
                :border="false"
                :clearable="false"
                :show-footer="false"
                unlink-panels
              />
            </ElConfigProvider>
          </div>
        </main>
      </div>

      <div v-if="!validation.valid" class="picker-error">{{ validation.message }}</div>
      <footer class="picker-footer">
        <el-button @click="closeWithoutApply">取消</el-button>
        <el-button type="primary" :disabled="!validation.valid" @click="applyDraft">应用</el-button>
      </footer>
    </div>
  </el-popover>
</template>

<style scoped>
.date-expression-trigger {
  width: 100%;
  min-width: 0;
  justify-content: flex-start;
  overflow: hidden;
  text-overflow: ellipsis;
}

.date-expression-picker {
  color: #1d2129;
}

.picker-header {
  display: flex;
  flex-direction: column;
  gap: 3px;
  padding: 2px 8px 12px;
  border-bottom: 1px solid #e5e6eb;
}

.picker-header .picker-title,
.picker-header span:last-child,
.endpoint-caption,
.preset-caption,
.endpoint-result {
  color: #86909c;
  font-size: 12px;
}

.picker-body {
  display: grid;
  grid-template-columns: 142px minmax(0, 1fr);
  min-height: 286px;
}

.preset-options {
  padding: 12px 10px;
  border-right: 1px solid #e5e6eb;
}

.preset-caption {
  display: block;
  margin: 0 4px 8px;
}

.preset-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 6px;
}

.preset-grid button,
.custom-range-button {
  min-height: 30px;
  padding: 0 8px;
  border: 0;
  border-radius: 4px;
  background: #f7f8fa;
  color: #4e5969;
  cursor: pointer;
}

.preset-grid button:hover,
.custom-range-button:hover {
  background: #f2f3f5;
}

.preset-grid button.active {
  background: #315efb;
  color: #fff;
}

.custom-range-button {
  display: flex;
  width: 100%;
  justify-content: space-between;
  align-items: center;
  margin-top: 8px;
}

.range-editor {
  display: flex;
  min-width: 0;
  flex-direction: column;
  gap: 10px;
  padding: 8px 10px;
}

.endpoint-controls {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
  padding: 4px 6px 10px;
  border-bottom: 1px solid #e5e6eb;
}

.endpoint-panel {
  display: flex;
  min-width: 0;
  flex-direction: column;
  gap: 12px;
}

.endpoint-mode,
.endpoint-panel :deep(.el-date-editor),
.endpoint-panel :deep(.el-input-number) {
  width: 100%;
}

.dynamic-input {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  align-items: center;
  gap: 8px;
  white-space: nowrap;
}

.calendar-panel {
  min-width: 0;
  overflow: hidden;
}

.calendar-panel :deep(.el-picker-panel) {
  width: 100%;
  border: 0;
  box-shadow: none;
}

.calendar-panel :deep(.el-date-range-picker) {
  width: 100%;
}

.calendar-panel :deep(.el-date-range-picker .el-picker-panel__body) {
  min-width: 0;
}

.calendar-panel :deep(.el-date-range-picker__content) {
  padding: 10px;
}

.picker-error {
  padding: 0 16px 8px;
  color: #f53f3f;
  font-size: 12px;
}

.picker-footer {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  padding: 10px 8px 2px;
  border-top: 1px solid #e5e6eb;
}

@media (max-width: 720px) {
  .picker-body {
    grid-template-columns: 132px minmax(0, 1fr);
  }

  .range-editor {
    overflow-x: auto;
  }

  .endpoint-controls {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
