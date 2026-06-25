const WORKSPACE_ADMIN_ROLES = new Set(['owner', 'admin'])

export interface WorkspaceRoleState {
  getTenantRole?: string
  tenantRole?: string
  workspaceRole?: string
  isPlatformWorkspaceDelegate?: boolean
  isSystemAdminUser?: boolean
}

export const normalizeWorkspaceRole = (role?: string | null) =>
  String(role || '').trim().toLowerCase()

export const canManageWorkspaceRole = (role?: string | null) =>
  WORKSPACE_ADMIN_ROLES.has(normalizeWorkspaceRole(role))

export const resolveWorkspaceRole = (state: WorkspaceRoleState) =>
  normalizeWorkspaceRole(state.getTenantRole || state.workspaceRole || state.tenantRole)

export const canManageCurrentWorkspace = (state: WorkspaceRoleState) => {
  if (state.isPlatformWorkspaceDelegate) return true
  if (state.isSystemAdminUser) return false
  return canManageWorkspaceRole(resolveWorkspaceRole(state))
}
