const DEFAULT_CHART_SIZE_Y = 14
const LEGACY_ANALYSIS_TABLE_SIZE_Y = 16
const DEFAULT_DASHBOARD_GRID_COLUMNS = 72
const MIN_CHART_SIZE_Y_WITH_INSIGHT = 16

const DASHBOARD_GRID_ROW_HEIGHT = 28
const DASHBOARD_GRID_GAP = 6
const VIEW_VERTICAL_CHROME_HEIGHT = 72
const TABLE_HEADER_ROW_HEIGHT = 32
const TABLE_DATA_ROW_HEIGHT = 30
const TABLE_BOTTOM_BUFFER = 12
const MIN_TABLE_SIZE_Y = 8
const MAX_TABLE_SIZE_Y = 24

const isTableViewInfo = (viewInfo?: any) => {
  const chart = viewInfo?.chart
  return chart?.type === 'table' || chart?.sourceType === 'table'
}

const getChartType = (viewInfo?: any) => viewInfo?.chart?.type || viewInfo?.chart?.sourceType

const getMetricCount = (viewInfo?: any) => {
  const yAxis = viewInfo?.chart?.yAxis
  return Array.isArray(yAxis) ? yAxis.filter((axis) => !axis?.hidden).length : 0
}

const getTableRowCount = (viewInfo?: any) => {
  const rows = viewInfo?.data?.data
  return Array.isArray(rows) ? rows.length : 0
}

export const getRecommendedTableComponentSizeY = (viewInfo?: any) => {
  const rowCount = Math.max(getTableRowCount(viewInfo), 1)
  const targetHeight =
    VIEW_VERTICAL_CHROME_HEIGHT +
    TABLE_HEADER_ROW_HEIGHT +
    rowCount * TABLE_DATA_ROW_HEIGHT +
    TABLE_BOTTOM_BUFFER
  const sizeY = Math.ceil((targetHeight + DASHBOARD_GRID_GAP) / DASHBOARD_GRID_ROW_HEIGHT)

  return Math.min(MAX_TABLE_SIZE_Y, Math.max(MIN_TABLE_SIZE_Y, sizeY))
}

export const applyRecommendedChartComponentSize = (component: any, viewInfo?: any) => {
  if (!component) {
    return component
  }

  if (isTableViewInfo(viewInfo)) {
    component.sizeY = getRecommendedTableComponentSizeY(viewInfo)
  } else if (getChartType(viewInfo) !== 'metric') {
    component.sizeY = Math.max(component.sizeY || DEFAULT_CHART_SIZE_Y, MIN_CHART_SIZE_Y_WITH_INSIGHT)
  }
  return component
}

export const getPreviewComponentSizeY = (component: any, viewInfo?: any) => {
  const currentSizeY = component?.sizeY || DEFAULT_CHART_SIZE_Y

  if (!component || !isTableViewInfo(viewInfo)) {
    return currentSizeY
  }

  const recommendedSizeY = getRecommendedTableComponentSizeY(viewInfo)
  const isLegacyDefaultHeight =
    currentSizeY === DEFAULT_CHART_SIZE_Y || currentSizeY === LEGACY_ANALYSIS_TABLE_SIZE_Y

  if (isLegacyDefaultHeight && recommendedSizeY < currentSizeY) {
    return recommendedSizeY
  }

  return currentSizeY
}

export const getRecommendedDashboardChartFrame = (viewInfo?: any, chartCount = 1) => {
  const chartType = getChartType(viewInfo)

  if (isTableViewInfo(viewInfo)) {
    return {
      sizeX: DEFAULT_DASHBOARD_GRID_COLUMNS,
      sizeY: getRecommendedTableComponentSizeY(viewInfo),
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
