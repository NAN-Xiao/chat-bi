<script setup lang="ts">
import { ref, watch } from 'vue'
import RoiChartCard from './RoiChartCard.vue'
import type { RoiChart, RoiLayoutSpan } from './types'
import { canManageRoiChart, moveRoiChart } from './roiChartGridBehavior'

const props = defineProps<{
  charts: RoiChart[]
  canEdit: boolean
  refreshingChartIds: string[]
}>()

const emit = defineEmits<{
  edit: [chart: RoiChart]
  remove: [chart: RoiChart]
  refresh: [chart: RoiChart]
  reorder: [charts: RoiChart[]]
  'span-change': [chart: RoiChart, span: RoiLayoutSpan]
}>()

const orderedCharts = ref<RoiChart[]>([])
const draggingIndex = ref<number | null>(null)
const layout_span: Record<RoiLayoutSpan, string> = {
  full: 'span-full',
  half: 'span-half',
  third: 'span-third',
}

watch(
  () => props.charts,
  (charts) => {
    orderedCharts.value = [...charts].sort((left, right) => left.sort - right.sort)
  },
  { immediate: true, deep: true }
)

function startDrag(chart: RoiChart, index: number, event: DragEvent) {
  if (!canManageRoiChart(chart, props.canEdit)) {
    event.preventDefault()
    return
  }
  draggingIndex.value = index
  event.dataTransfer?.setData('text/plain', String(chart.id))
  if (event.dataTransfer) event.dataTransfer.effectAllowed = 'move'
}

function dropAt(index: number) {
  if (draggingIndex.value === null) return
  const reordered = moveRoiChart(orderedCharts.value, draggingIndex.value, index)
  draggingIndex.value = null
  orderedCharts.value = reordered
  emit('reorder', reordered)
}
</script>

<template>
  <div class="roi-chart-grid">
    <div
      v-for="(chart, index) in orderedCharts"
      :key="chart.id"
      class="roi-chart-grid__item"
      :class="layout_span[chart.layout_span]"
      :draggable="canManageRoiChart(chart, canEdit)"
      @dragstart="startDrag(chart, index, $event)"
      @dragover.prevent
      @drop.prevent="dropAt(index)"
      @dragend="draggingIndex = null"
    >
      <RoiChartCard
        :chart="chart"
        :can-edit="canEdit"
        :refreshing="refreshingChartIds.includes(String(chart.id))"
        @refresh="emit('refresh', $event)"
        @edit="emit('edit', $event)"
        @remove="emit('remove', $event)"
        @span-change="(item, span) => emit('span-change', item, span)"
      />
    </div>
  </div>
</template>

<style scoped lang="less">
.roi-chart-grid {
  display: grid;
  grid-template-columns: repeat(6, minmax(0, 1fr));
  grid-auto-flow: row;
  grid-auto-rows: minmax(320px, auto);
  gap: 16px;
  width: 100%;
  min-width: 0;
}

.roi-chart-grid__item {
  min-width: 0;
  min-height: 320px;
}

.span-full {
  grid-column: span 6;
}

.span-half {
  grid-column: span 3;
}

.span-third {
  grid-column: span 2;
}

@media (max-width: 1200px) {
  .roi-chart-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .span-full {
    grid-column: span 2;
  }

  .span-half,
  .span-third {
    grid-column: span 1;
  }
}

@media (max-width: 720px) {
  .roi-chart-grid {
    grid-template-columns: minmax(0, 1fr);
  }

  .span-full,
  .span-half,
  .span-third {
    grid-column: span 1;
  }
}
</style>
