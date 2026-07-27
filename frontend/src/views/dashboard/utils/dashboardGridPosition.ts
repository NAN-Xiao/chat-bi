type DashboardGridComponent = {
  y?: unknown
  sizeY?: unknown
}

export function getDashboardGridCellWidth(
  containerWidth: number,
  columnCount: number,
  gridGap: number,
  edgeGap: number
): number {
  const safeContainerWidth = Number.isFinite(containerWidth) ? Math.max(0, containerWidth) : 0
  const safeColumnCount = Number.isFinite(columnCount)
    ? Math.max(1, Math.round(columnCount))
    : 1
  const safeGridGap = Number.isFinite(gridGap) ? Math.max(0, gridGap) : 0
  const safeEdgeGap = Number.isFinite(edgeGap) ? Math.max(0, edgeGap) : 0
  const availableWidth = Math.max(0, safeContainerWidth - safeEdgeGap * 2)

  return (availableWidth + safeGridGap) / safeColumnCount
}

export function normalizeDashboardGridCoordinate(value: unknown): number {
  const coordinate = Number(value)
  return Number.isFinite(coordinate) ? Math.max(1, Math.round(coordinate)) : 1
}

function normalizeDashboardGridSize(value: unknown): number {
  const size = Number(value)
  return Number.isFinite(size) ? Math.max(1, Math.round(size)) : 1
}

export function getDashboardGridContentRows(components: DashboardGridComponent[]): number {
  return components.reduce((contentRows, component) => {
    const componentBottom =
      normalizeDashboardGridCoordinate(component.y) - 1 + normalizeDashboardGridSize(component.sizeY)
    return Math.max(contentRows, componentBottom)
  }, 0)
}

export function getNextDashboardComponentY(components: DashboardGridComponent[]): number {
  return components.reduce((bottomPosition, component) => {
    const componentBottom =
      normalizeDashboardGridCoordinate(component.y) + normalizeDashboardGridSize(component.sizeY)
    return Math.max(bottomPosition, componentBottom)
  }, 1)
}
