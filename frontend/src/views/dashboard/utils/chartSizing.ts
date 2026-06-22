const DEFAULT_CHART_SIZE_Y = 14
const LEGACY_ANALYSIS_TABLE_SIZE_Y = 16

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
  if (component && isTableViewInfo(viewInfo)) {
    component.sizeY = getRecommendedTableComponentSizeY(viewInfo)
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
