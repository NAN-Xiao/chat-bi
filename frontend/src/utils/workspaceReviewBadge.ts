import { canManageWorkspaceRole } from './workspacePermission.ts'

export interface WorkspaceReviewBadgeContext {
  tenantId?: string | number | null
  role?: string | null
  isSystemAdminUser?: boolean
  isPlatformWorkspaceDelegate?: boolean
}

interface WorkspaceReviewApplication {
  status?: string | null
}

type FetchPendingWorkspaceReviews = () => Promise<
  WorkspaceReviewApplication[] | null | undefined
>

export const shouldLoadWorkspaceReviews = (context: WorkspaceReviewBadgeContext) =>
  Boolean(context.tenantId) &&
  !context.isSystemAdminUser &&
  !context.isPlatformWorkspaceDelegate &&
  canManageWorkspaceRole(context.role)

export const shouldShowWorkspaceReviewBadge = (
  context: WorkspaceReviewBadgeContext,
  pendingCount: number
) => shouldLoadWorkspaceReviews(context) && pendingCount > 0

export const createLatestWorkspaceReviewLoader = (fetchPending: FetchPendingWorkspaceReviews) => {
  let latestRequestId = 0

  return async (context: WorkspaceReviewBadgeContext): Promise<number | null> => {
    const requestId = ++latestRequestId
    if (!shouldLoadWorkspaceReviews(context)) return 0

    try {
      const rows = (await fetchPending()) || []
      if (requestId !== latestRequestId) return null
      return rows.filter((item) => item.status === 'pending').length
    } catch {
      if (requestId !== latestRequestId) return null
      return 0
    }
  }
}
