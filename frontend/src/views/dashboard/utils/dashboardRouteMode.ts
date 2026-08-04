export type OrdinaryDashboardMode = 'default' | 'my'

export const firstDashboardMode = (value: unknown) => {
  const mode = Array.isArray(value) ? value[0] : value
  return typeof mode === 'string' ? mode : ''
}

export const resolveOrdinaryDashboardMode = (
  value: unknown,
  defaultMode = false
): OrdinaryDashboardMode => {
  if (defaultMode) return 'default'
  return firstDashboardMode(value) === 'default' ? 'default' : 'my'
}

export const isUnsupportedDashboardMode = (value: unknown) => {
  const mode = firstDashboardMode(value)
  return !!mode && mode !== 'default' && mode !== 'my'
}

export const buildOrdinaryDashboardQuery = (
  resourceId: string | number,
  dashboardMode: unknown
) => ({
  resourceId,
  dashboardMode: resolveOrdinaryDashboardMode(dashboardMode),
})
