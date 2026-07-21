type DashboardGridComponent = {
  y?: unknown
  sizeY?: unknown
}

export function normalizeDashboardGridCoordinate(value: unknown): number {
  const coordinate = Number(value)
  return Number.isFinite(coordinate) ? Math.max(1, Math.round(coordinate)) : 1
}

function normalizeDashboardGridSize(value: unknown): number {
  const size = Number(value)
  return Number.isFinite(size) ? Math.max(1, Math.round(size)) : 1
}

export function getNextDashboardComponentY(components: DashboardGridComponent[]): number {
  return components.reduce((bottomPosition, component) => {
    const componentBottom =
      normalizeDashboardGridCoordinate(component.y) + normalizeDashboardGridSize(component.sizeY)
    return Math.max(bottomPosition, componentBottom)
  }, 1)
}
