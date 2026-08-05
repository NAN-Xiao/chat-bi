import type { ChartMountTarget } from '@/views/chat/component/BaseChart.ts'
import { RadialPartitionChart } from '@/views/chat/component/charts/RadialPartitionChart.ts'

export class Donut extends RadialPartitionChart {
  constructor(mountTarget: ChartMountTarget) {
    super(mountTarget, {
      name: 'donut',
      innerRadius: 0.55,
      showPercentage: true,
    })
  }
}
