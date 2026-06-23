export const PLATFORM_ADMIN_HOME = '/system/platform-overview'
export const TENANT_ADMIN_HOME = '/system/overview'
export const MEMBER_HOME = '/chat/index'
export const WORKSPACE_REQUIRED_HOME = '/account/workspaces'

export interface NavigationUserState {
  isPlatformWorkspaceDelegate?: boolean
  isSystemAdminUser?: boolean
  isTenantAdminUser?: boolean
  hasActiveWorkspace?: boolean
}

const hasWorkspace = (userStore: NavigationUserState) =>
  userStore.hasActiveWorkspace === true || userStore.isPlatformWorkspaceDelegate === true

export const resolveAuthenticatedHome = (userStore: NavigationUserState) => {
  if (userStore.isPlatformWorkspaceDelegate) return TENANT_ADMIN_HOME
  if (userStore.isSystemAdminUser) return PLATFORM_ADMIN_HOME
  if (!hasWorkspace(userStore)) return WORKSPACE_REQUIRED_HOME
  return userStore.isTenantAdminUser ? TENANT_ADMIN_HOME : MEMBER_HOME
}

export const resolveSystemHome = (userStore: NavigationUserState) => {
  if (userStore.isPlatformWorkspaceDelegate) return TENANT_ADMIN_HOME
  if (userStore.isSystemAdminUser) return PLATFORM_ADMIN_HOME
  if (userStore.isTenantAdminUser) return TENANT_ADMIN_HOME
  return hasWorkspace(userStore) ? MEMBER_HOME : WORKSPACE_REQUIRED_HOME
}

export const resolveManagementHome = (userStore: NavigationUserState) => {
  if (userStore.isSystemAdminUser && !userStore.isPlatformWorkspaceDelegate) {
    return PLATFORM_ADMIN_HOME
  }
  if (userStore.isTenantAdminUser || userStore.isPlatformWorkspaceDelegate) {
    return TENANT_ADMIN_HOME
  }
  return hasWorkspace(userStore) ? MEMBER_HOME : WORKSPACE_REQUIRED_HOME
}

export const resolveBusinessHome = (userStore: NavigationUserState) => {
  if (userStore.isSystemAdminUser && !userStore.isPlatformWorkspaceDelegate) {
    return PLATFORM_ADMIN_HOME
  }
  return hasWorkspace(userStore) ? MEMBER_HOME : WORKSPACE_REQUIRED_HOME
}

export const resolveAfterWorkspaceSwitch = resolveAuthenticatedHome

export const resolveLoginSuccessTarget = (
  userStore: NavigationUserState,
  redirect?: string | null
) => {
  if (redirect && !redirect.startsWith('/login') && !redirect.startsWith('/admin-login')) {
    return redirect
  }
  return resolveAuthenticatedHome(userStore)
}
