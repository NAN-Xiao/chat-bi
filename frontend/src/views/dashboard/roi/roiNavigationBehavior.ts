import { canAccessRoiDashboard } from '@/utils/workspacePermission'

export { canAccessRoiDashboard }

export type RoiDashboardScope = 'default' | 'roi' | 'my'

export const shouldResetOrdinaryDashboardStore = (scope: RoiDashboardScope) => scope !== 'roi'

export const createDashboardNodeClickPlan = (scope: RoiDashboardScope) => ({
  resetOrdinaryDashboardSelection: shouldResetOrdinaryDashboardStore(scope),
  syncRoute: true,
  emitNodeClick: true,
})

export const resolveRoiPreviewAccessPlan = (
  scope: RoiDashboardScope,
  canAccessRoi: boolean
) => {
  const isRoiRoute = scope === 'roi'
  return {
    shortCircuitOrdinaryDashboard: isRoiRoute,
    renderRoiDashboard: isRoiRoute && canAccessRoi,
    redirectToLanding: isRoiRoute && !canAccessRoi,
  }
}

export const shouldInitializeOrdinaryDashboardCanvas = (
  showPosition: string,
  scope: RoiDashboardScope
) => showPosition === 'preview' && scope !== 'roi'

export const createRoiEntryRouteQuery = (query: Record<string, unknown>) => {
  const nextQuery = { ...query }
  delete nextQuery.resourceId
  delete nextQuery.dashboardId
  return { ...nextQuery, dashboardMode: 'roi' as const }
}

export const resolveInitialDashboardRoutePlan = (
  scope: RoiDashboardScope,
  resourceId: unknown,
  hasFirstRoiDashboard: boolean
) => {
  const isEmptyRoiRoute = scope === 'roi' && !resourceId
  return {
    isEmptyRoiRoute,
    waitForRoiBranch: isEmptyRoiRoute,
    selectFirstRoiDashboard: isEmptyRoiRoute && hasFirstRoiDashboard,
    clearSelection: isEmptyRoiRoute && !hasFirstRoiDashboard,
    allowOrdinaryDashboardFallback: !isEmptyRoiRoute,
  }
}

export const isAllowedRoiGroupOperation = (operation: string) =>
  operation === 'newRoiDashboard' || operation === 'toggleTreeEditing'

type TreeBranchPublication<T> = {
  request: Promise<T[]>
  isCurrent: () => boolean
  publish: (nodes: T[]) => void
  complete: () => void
  onError?: (error: unknown) => void
}

export const publishCurrentTreeBranch = async <T>({
  request,
  isCurrent,
  publish,
  complete,
  onError,
}: TreeBranchPublication<T>) => {
  try {
    const nodes = await request
    if (!isCurrent()) return
    publish(nodes || [])
  } catch (error) {
    if (!isCurrent()) return
    onError?.(error)
    publish([])
  }
  if (isCurrent()) complete()
}
