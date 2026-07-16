export type RoiDashboardScope = 'default' | 'roi' | 'my'

export const createDashboardNodeClickPlan = (scope: RoiDashboardScope) => ({
  resetOrdinaryDashboardSelection: scope !== 'roi',
  syncRoute: true,
  emitNodeClick: true,
})

export const shouldInitializeOrdinaryDashboardCanvas = (
  showPosition: string,
  scope: RoiDashboardScope
) => showPosition === 'preview' && scope !== 'roi'

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
