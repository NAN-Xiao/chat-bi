import type { RoiDashboardScope } from '@/views/dashboard/roi/roiNavigationBehavior'

export type RoiLandingRedirectSnapshot = {
  tenantId: string
  resourceId: string
  mode: RoiDashboardScope
  canAccessRoi: boolean
}

type RoiLandingRedirectRequest<T> = {
  snapshot: RoiLandingRedirectSnapshot
  getCurrentSnapshot: () => RoiLandingRedirectSnapshot
  resolveLanding: () => Promise<T>
  commit: (target: T) => void | Promise<void>
}

const isSameSnapshot = (
  expected: RoiLandingRedirectSnapshot,
  current: RoiLandingRedirectSnapshot
) =>
  expected.tenantId === current.tenantId &&
  expected.resourceId === current.resourceId &&
  expected.mode === current.mode &&
  expected.canAccessRoi === current.canAccessRoi

export const createRoiLandingRedirectCoordinator = () => {
  let generation = 0
  let activeToken: number | null = null

  return {
    async redirect<T>({
      snapshot,
      getCurrentSnapshot,
      resolveLanding,
      commit,
    }: RoiLandingRedirectRequest<T>) {
      const token = ++generation
      activeToken = token
      try {
        const target = await resolveLanding()
        if (activeToken !== token || !isSameSnapshot(snapshot, getCurrentSnapshot())) return
        await commit(target)
      } catch (error) {
        if (activeToken === token && isSameSnapshot(snapshot, getCurrentSnapshot())) throw error
      } finally {
        if (activeToken === token) activeToken = null
      }
    },
    invalidate() {
      generation += 1
      activeToken = null
    },
    isResolving() {
      return activeToken !== null
    },
  }
}

export const runRoiLandingRedirect = async (
  task: () => Promise<void>,
  onError: (error: unknown) => void
) => {
  try {
    await task()
  } catch (error) {
    onError(error)
  }
}
