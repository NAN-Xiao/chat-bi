import { useCache } from '@/utils/useCache.ts'

const { wsCache } = useCache('sessionStorage')
const DRAFT_PREFIX = 'dashboard.canvas.draft.'

export const getDashboardCanvasSourceKey = (resourceId?: string | number | null) =>
  resourceId ? `dashboard:${resourceId}` : null

export const getCreateCanvasSourceKey = (
  datasource?: string | number | null,
  pid?: string | number | null
) => `create:${datasource || 'default'}:${pid || 'root'}`

export const getDashboardCanvasDraftKey = (sourceKey: string) => `${DRAFT_PREFIX}${sourceKey}`

export const loadDashboardCanvasDraft = (sourceKey: string) =>
  wsCache.get(getDashboardCanvasDraftKey(sourceKey))

export const saveDashboardCanvasDraft = (sourceKey: string, payload: any) => {
  wsCache.set(getDashboardCanvasDraftKey(sourceKey), payload)
}

export const clearDashboardCanvasDraft = (sourceKey?: string | null) => {
  if (!sourceKey) return
  wsCache.delete(getDashboardCanvasDraftKey(sourceKey))
}
