import type { ChartMountTarget } from '@/views/chat/component/BaseChart.ts'
import { Column } from '@/views/chat/component/charts/Column.ts'

export class GroupedColumn extends Column {
  constructor(mountTarget: ChartMountTarget) {
    super(mountTarget, {
      chartName: 'grouped_column',
      seriesLayout: 'grouped',
    })
  }
}
