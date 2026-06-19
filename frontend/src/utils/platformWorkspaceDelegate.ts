import { useCache } from '@/utils/useCache'

export const PLATFORM_WORKSPACE_DELEGATE_QUERY_KEY = 'platform_workspace_delegate'
export const PLATFORM_WORKSPACE_DELEGATE_TENANT_QUERY_KEY = 'tenant_id'
export const PLATFORM_WORKSPACE_DELEGATE_HEADER = 'X-ZHISHU-PLATFORM-WORKSPACE-DELEGATE'

const { wsCache: sessionCache } = useCache('sessionStorage')

const DELEGATE_FLAG_KEY = 'user.platformWorkspaceDelegate'
const DELEGATE_TENANT_ID_KEY = 'user.platformWorkspaceDelegateTenantId'
const DELEGATE_TENANT_CODE_KEY = 'user.platformWorkspaceDelegateTenantCode'
const DELEGATE_TENANT_NAME_KEY = 'user.platformWorkspaceDelegateTenantName'

export interface PlatformWorkspaceDelegateTenant {
  id: number | string
  code?: string
  name?: string
}

const firstQueryValue = (value: unknown): string => {
  if (Array.isArray(value)) {
    return value[0] ? String(value[0]) : ''
  }
  return value ? String(value) : ''
}

export const setPlatformWorkspaceDelegateContext = (
  tenant: PlatformWorkspaceDelegateTenant
) => {
  const tenantId = String(tenant.id || '')
  if (!tenantId) return false
  sessionCache.set(DELEGATE_FLAG_KEY, '1')
  sessionCache.set(DELEGATE_TENANT_ID_KEY, tenantId)
  sessionCache.set(DELEGATE_TENANT_CODE_KEY, tenant.code ? String(tenant.code) : '')
  sessionCache.set(DELEGATE_TENANT_NAME_KEY, tenant.name ? String(tenant.name) : '')
  return true
}

export const clearPlatformWorkspaceDelegateContext = () => {
  sessionCache.delete(DELEGATE_FLAG_KEY)
  sessionCache.delete(DELEGATE_TENANT_ID_KEY)
  sessionCache.delete(DELEGATE_TENANT_CODE_KEY)
  sessionCache.delete(DELEGATE_TENANT_NAME_KEY)
}

export const isPlatformWorkspaceDelegateSession = () =>
  sessionCache.get(DELEGATE_FLAG_KEY) === '1' && !!sessionCache.get(DELEGATE_TENANT_ID_KEY)

export const getPlatformWorkspaceDelegateTenantId = () =>
  isPlatformWorkspaceDelegateSession() ? String(sessionCache.get(DELEGATE_TENANT_ID_KEY)) : ''

export const applyPlatformWorkspaceDelegateRouteQuery = (query: Record<string, unknown>) => {
  const enabled = firstQueryValue(query[PLATFORM_WORKSPACE_DELEGATE_QUERY_KEY]) === '1'
  const tenantId = firstQueryValue(query[PLATFORM_WORKSPACE_DELEGATE_TENANT_QUERY_KEY])
  if (!enabled || !tenantId) return false
  return setPlatformWorkspaceDelegateContext({
    id: tenantId,
    code: firstQueryValue(query.tenant_code),
    name: firstQueryValue(query.tenant_name),
  })
}
