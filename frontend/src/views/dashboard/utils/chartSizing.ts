const DEFAULT_CHART_SIZE_Y = 14
const DEFAULT_DASHBOARD_GRID_COLUMNS = 72
const MIN_CHART_SIZE_Y_WITH_INSIGHT = 16

const getChartType = (viewInfo?: any) => viewInfo?.chart?.type || viewInfo?.chart?.sourceType

const getMetricCount = (viewInfo?: any) => {
  const yAxis = viewInfo?.chart?.yAxis
  return Array.isArray(yAxis) ? yAxis.filter((axis) => !axis?.hidden).length : 0
}

export const applyRecommendedChartComponentSize = (component: any, viewInfo?: any) => {
  if (!component) {
    return component
  }

  const chartType = getChartType(viewInfo)
  if (chartType !== 'table' && chartType !== 'metric') {
    component.sizeY = Math.max(component.sizeY || DEFAULT_CHART_SIZE_Y, MIN_CHART_SIZE_Y_WITH_INSIGHT)
  }
  return component
}

export const getRecommendedDashboardChartFrame = (viewInfo?: any, chartCount = 1) => {
  const chartType = getChartType(viewInfo)

  if (chartType === 'table') {
    return {
      sizeX: DEFAULT_DASHBOARD_GRID_COLUMNS,
      sizeY: DEFAULT_CHART_SIZE_Y,
    }
  }

  if (chartType === 'metric') {
    const metricCount = getMetricCount(viewInfo)
    return {
      sizeX:
        chartCount <= 1
          ? DEFAULT_DASHBOARD_GRID_COLUMNS
          : metricCount >= 3
            ? DEFAULT_DASHBOARD_GRID_COLUMNS
            : metricCount >= 2
              ? 36
              : 24,
      sizeY: 8,
    }
  }

  if (chartType === 'sankey' || chartType === 'treemap' || chartType === 'heatmap') {
    return {
      sizeX: DEFAULT_DASHBOARD_GRID_COLUMNS,
      sizeY: 20,
    }
  }

  if (chartType === 'line' || chartType === 'area' || chartType === 'bar' || chartType === 'column' || chartType === 'scatter') {
    return {
      sizeX: chartCount <= 2 ? DEFAULT_DASHBOARD_GRID_COLUMNS : 48,
      sizeY: 18,
    }
  }

  if (chartType === 'pie' || chartType === 'funnel') {
    return {
      sizeX: chartCount <= 2 ? 36 : 24,
      sizeY: 16,
    }
  }

  return {
    sizeX: chartCount <= 1 ? DEFAULT_DASHBOARD_GRID_COLUMNS : 36,
    sizeY: MIN_CHART_SIZE_Y_WITH_INSIGHT,
  }
}

export const layoutDashboardChartComponents = (
  components: Array<any>,
  viewInfoMap: Record<string, any>,
  columnCount = DEFAULT_DASHBOARD_GRID_COLUMNS,
  options: { singleColumn?: boolean } = {}
) => {
  const rowGap = 1
  let cursorX = 1
  let cursorY = 1
  let rowHeight = 0

  components.forEach((component) => {
    const viewInfo = viewInfoMap?.[component.id]
    const frame = getRecommendedDashboardChartFrame(viewInfo, components.length)
    const sizeX = options.singleColumn
      ? columnCount
      : Math.min(Math.max(frame.sizeX, 1), columnCount)
    const sizeY = Math.max(frame.sizeY, 1)

    if (cursorX > 1 && cursorX + sizeX - 1 > columnCount) {
      cursorX = 1
      cursorY += rowHeight + rowGap
      rowHeight = 0
    }

    component.x = cursorX
    component.y = cursorY
    component.sizeX = sizeX
    component.sizeY = sizeY

    cursorX += sizeX
    rowHeight = Math.max(rowHeight, sizeY)
  })

  return components
}
