import { type TenantInfo } from '@/api/tenant'
import { useCache } from '@/utils/useCache'

const { wsCache } = useCache('sessionStorage')
const ADMIN_BUSINESS_TENANT_KEY = 'workspace-admin.business-tenant'

export const rememberBusinessTenantBeforeAdmin = (tenant: Partial<TenantInfo> | null) => {
  if (!tenant?.id) {
    wsCache.delete(ADMIN_BUSINESS_TENANT_KEY)
    return
  }
  wsCache.set(ADMIN_BUSINESS_TENANT_KEY, {
    id: tenant.id,
    public_id: tenant.public_id || '',
    name: tenant.name || '',
    role: tenant.role || '',
  })
}

export const getRememberedBusinessTenant = (): Partial<TenantInfo> | null => {
  const tenant = wsCache.get(ADMIN_BUSINESS_TENANT_KEY)
  return tenant?.id ? tenant : null
}

export const clearRememberedBusinessTenant = () => {
  wsCache.delete(ADMIN_BUSINESS_TENANT_KEY)
}
