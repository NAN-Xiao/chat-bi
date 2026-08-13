import { canManageCurrentWorkspace, type WorkspaceRoleState } from './workspacePermission.ts'

export interface CurrentWorkspaceAdminState extends WorkspaceRoleState {
  getTenantId?: string | number
  getTenantPublicId?: string
  getTenantName?: string
}

export interface CurrentWorkspaceAdminTenant {
  id: string
  public_id: string
  name: string
  role: string
}

export interface CurrentWorkspaceAdminActions {
  remember: (tenant: CurrentWorkspaceAdminTenant) => void
  navigate: () => unknown | Promise<unknown>
}

export const resolveCurrentWorkspaceAdminTenant = (
  state: CurrentWorkspaceAdminState
): CurrentWorkspaceAdminTenant | null => {
  const tenantId = String(state.getTenantId || '').trim()
  if (!tenantId || !canManageCurrentWorkspace(state)) return null
  return {
    id: tenantId,
    public_id: String(state.getTenantPublicId || ''),
    name: String(state.getTenantName || ''),
    role: String(state.getTenantRole || ''),
  }
}

export const enterCurrentWorkspaceAdmin = async (
  state: CurrentWorkspaceAdminState,
  actions: CurrentWorkspaceAdminActions
) => {
  const tenant = resolveCurrentWorkspaceAdminTenant(state)
  if (!tenant) return false
  actions.remember(tenant)
  await actions.navigate()
  return true
}
