import { canManageWorkspaceRole } from './workspacePermission.ts'

export interface WorkspaceNotificationBadgeContext {
  tenantId?: string | number | null
  role?: string | null
  isSystemAdminUser?: boolean
  isPlatformWorkspaceDelegate?: boolean
}

interface WorkspaceNotification {
  status?: string | null
}

type FetchPendingWorkspaceNotifications = () => Promise<
  WorkspaceNotification[] | null | undefined
>

interface WorkspaceNotificationFetchers {
  fetchPendingReviews: FetchPendingWorkspaceNotifications
  fetchPendingInvitations: FetchPendingWorkspaceNotifications
}

const isBusinessWorkspaceUser = (context: WorkspaceNotificationBadgeContext) =>
  !context.isSystemAdminUser && !context.isPlatformWorkspaceDelegate

export const shouldLoadWorkspaceReviews = (context: WorkspaceNotificationBadgeContext) =>
  Boolean(context.tenantId) &&
  isBusinessWorkspaceUser(context) &&
  canManageWorkspaceRole(context.role)

export const shouldLoadWorkspaceNotifications = (context: WorkspaceNotificationBadgeContext) =>
  isBusinessWorkspaceUser(context)

export const shouldShowWorkspaceNotificationBadge = (
  context: WorkspaceNotificationBadgeContext,
  pendingCount: number
) => shouldLoadWorkspaceNotifications(context) && pendingCount > 0

const countPending = async (fetchPending: FetchPendingWorkspaceNotifications) => {
  try {
    const rows = (await fetchPending()) || []
    return rows.filter((item) => item.status === 'pending').length
  } catch {
    return 0
  }
}

export const createLatestWorkspaceNotificationLoader = (
  fetchers: WorkspaceNotificationFetchers
) => {
  let latestRequestId = 0

  return async (context: WorkspaceNotificationBadgeContext): Promise<number | null> => {
    const requestId = ++latestRequestId
    if (!shouldLoadWorkspaceNotifications(context)) return 0

    const pendingCounts = [countPending(fetchers.fetchPendingInvitations)]
    if (shouldLoadWorkspaceReviews(context)) {
      pendingCounts.push(countPending(fetchers.fetchPendingReviews))
    }

    const total = (await Promise.all(pendingCounts)).reduce((sum, count) => sum + count, 0)
    if (requestId !== latestRequestId) return null
    return total
  }
}
