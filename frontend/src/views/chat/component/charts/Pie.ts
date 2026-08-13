import type { ChartMountTarget } from '@/views/chat/component/BaseChart.ts'
import { RadialPartitionChart } from '@/views/chat/component/charts/RadialPartitionChart.ts'

export class Pie extends RadialPartitionChart {
  constructor(mountTarget: ChartMountTarget) {
    super(mountTarget, {
      name: 'pie',
      innerRadius: 0,
      showPercentage: false,
    })
  }
}
