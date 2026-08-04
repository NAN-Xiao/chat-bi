import {
  WorkspaceContextMismatchError,
  WorkspaceContextStaleError,
} from './workspaceContextCore.ts'

export interface PlatformWorkspaceDelegateRequestSnapshot {
  active: boolean
  tenantId: string
  generation: number
}

const normalizeTenantId = (tenantId: unknown) => String(tenantId || '').trim()

export const createPlatformWorkspaceDelegateRequestContext = (initialTenantId = '') => {
  let tenantId = normalizeTenantId(initialTenantId)
  let generation = 0

  const capture = (): PlatformWorkspaceDelegateRequestSnapshot =>
    Object.freeze({
      active: Boolean(tenantId),
      tenantId,
      generation,
    })

  const update = (nextTenantId: unknown) => {
    const normalizedTenantId = normalizeTenantId(nextTenantId)
    if (normalizedTenantId === tenantId) return false
    tenantId = normalizedTenantId
    generation += 1
    return true
  }

  const assertCurrent = (
    snapshot: PlatformWorkspaceDelegateRequestSnapshot | undefined,
    responseTenantId = ''
  ) => {
    if (!snapshot) return
    if (
      snapshot.generation !== generation ||
      snapshot.active !== Boolean(tenantId) ||
      snapshot.tenantId !== tenantId
    ) {
      throw new WorkspaceContextStaleError('Platform workspace delegate context is stale')
    }
    const normalizedResponseTenantId = normalizeTenantId(responseTenantId)
    if (
      snapshot.active &&
      normalizedResponseTenantId &&
      normalizedResponseTenantId !== snapshot.tenantId
    ) {
      throw new WorkspaceContextMismatchError('平台代理工作空间校验失败，请刷新后重试')
    }
  }

  return {
    capture,
    update,
    assertCurrent,
  }
}

export type PlatformWorkspaceDelegateRequestContext = ReturnType<
  typeof createPlatformWorkspaceDelegateRequestContext
>
