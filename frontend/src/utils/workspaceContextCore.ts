export type WorkspacePhase = 'bootstrapping' | 'ready' | 'switching'
export type WorkspaceRequestMode = 'normal' | 'bootstrap' | 'switch' | 'none'

export interface WorkspaceContextState {
  activeTenantId: string
  pendingTenantId: string
  phase: WorkspacePhase
  epoch: number
  switchId: number
}

export interface WorkspaceRequestSnapshot {
  tenantId: string
  epoch: number
  phase: WorkspacePhase
  mode: WorkspaceRequestMode
  switchId?: number
}

export interface WorkspaceSwitchTransaction {
  previousTenantId: string
  targetTenantId: string
  epoch: number
  switchId: number
}

export interface WorkspaceContextStorage {
  getItem(key: string): string | null
  setItem(key: string, value: string): void
  removeItem(key: string): void
}

export const WORKSPACE_TENANT_STORAGE_KEY = 'user.activeTenantId'

export class WorkspaceContextStaleError extends Error {
  readonly code = 'WORKSPACE_CONTEXT_STALE'

  constructor(message = 'Workspace context is no longer current') {
    super(message)
    this.name = 'WorkspaceContextStaleError'
  }
}

const normalizeTenantId = (tenantId: unknown) => String(tenantId || '').trim()

const stale = (message: string): never => {
  throw new WorkspaceContextStaleError(message)
}

export const isWorkspaceContextStaleError = (
  error: unknown
): error is WorkspaceContextStaleError =>
  error instanceof WorkspaceContextStaleError ||
  (typeof error === 'object' &&
    error !== null &&
    (error as { code?: string }).code === 'WORKSPACE_CONTEXT_STALE')

export const createWorkspaceContextCore = (
  storage: WorkspaceContextStorage,
  providedState?: WorkspaceContextState
) => {
  const state: WorkspaceContextState =
    providedState || {
      activeTenantId: '',
      pendingTenantId: '',
      phase: 'bootstrapping',
      epoch: 0,
      switchId: 0,
    }

  const persistActiveTenant = () => {
    if (state.activeTenantId) {
      storage.setItem(WORKSPACE_TENANT_STORAGE_KEY, state.activeTenantId)
    } else {
      storage.removeItem(WORKSPACE_TENANT_STORAGE_KEY)
    }
  }

  const restore = () => {
    state.activeTenantId = normalizeTenantId(storage.getItem(WORKSPACE_TENANT_STORAGE_KEY))
    state.pendingTenantId = ''
    state.phase = 'bootstrapping'
    state.epoch += 1
    return state.activeTenantId
  }

  const isCurrentSwitch = (
    transactionOrTenantId: WorkspaceSwitchTransaction | string,
    switchId?: number
  ) => {
    const targetTenantId =
      typeof transactionOrTenantId === 'string'
        ? transactionOrTenantId
        : transactionOrTenantId.targetTenantId
    const expectedSwitchId =
      typeof transactionOrTenantId === 'string' ? switchId : transactionOrTenantId.switchId
    const expectedEpoch =
      typeof transactionOrTenantId === 'string' ? state.epoch : transactionOrTenantId.epoch
    return (
      state.phase === 'switching' &&
      state.epoch === expectedEpoch &&
      state.switchId === expectedSwitchId &&
      state.pendingTenantId === targetTenantId
    )
  }

  const beginSwitch = (targetTenantId: string): WorkspaceSwitchTransaction | null => {
    const normalizedTarget = normalizeTenantId(targetTenantId)
    if (!normalizedTarget) return null
    if (
      (state.phase === 'ready' && normalizedTarget === state.activeTenantId) ||
      (state.phase === 'switching' && normalizedTarget === state.pendingTenantId)
    ) {
      return null
    }

    state.epoch += 1
    state.switchId += 1
    state.pendingTenantId = normalizedTarget
    state.phase = 'switching'
    return Object.freeze({
      previousTenantId: state.activeTenantId,
      targetTenantId: normalizedTarget,
      epoch: state.epoch,
      switchId: state.switchId,
    })
  }

  const commitSwitch = (transaction: WorkspaceSwitchTransaction) => {
    if (!isCurrentSwitch(transaction)) return false
    state.activeTenantId = transaction.targetTenantId
    persistActiveTenant()
    return true
  }

  const finishSwitch = (transaction: WorkspaceSwitchTransaction) => {
    if (!isCurrentSwitch(transaction) || state.activeTenantId !== transaction.targetTenantId) {
      return false
    }
    state.pendingTenantId = ''
    state.phase = 'ready'
    return true
  }

  const rollbackSwitch = (transaction: WorkspaceSwitchTransaction) => {
    if (!isCurrentSwitch(transaction)) return false
    state.activeTenantId = transaction.previousTenantId
    state.pendingTenantId = ''
    state.phase = 'ready'
    persistActiveTenant()
    return true
  }

  const completeBootstrap = (serverTenantId: string) => {
    const previousTenantId = state.activeTenantId
    state.activeTenantId = normalizeTenantId(serverTenantId)
    state.pendingTenantId = ''
    state.phase = 'ready'
    persistActiveTenant()
    return {
      previousTenantId,
      activeTenantId: state.activeTenantId,
      replaced: Boolean(previousTenantId && previousTenantId !== state.activeTenantId),
    }
  }

  const clearActiveTenant = () => {
    state.epoch += 1
    state.switchId += 1
    state.activeTenantId = ''
    state.pendingTenantId = ''
    state.phase = 'ready'
    persistActiveTenant()
  }

  const captureRequest = (
    mode: WorkspaceRequestMode = 'normal',
    explicitTenantId = '',
    explicitSwitchId?: number
  ): WorkspaceRequestSnapshot => {
    if (mode === 'normal') {
      if (state.phase !== 'ready') {
        return stale('Workspace is not ready for ordinary requests')
      }
      return Object.freeze({
        tenantId: state.activeTenantId,
        epoch: state.epoch,
        phase: state.phase,
        mode,
      })
    }

    if (mode === 'switch') {
      const tenantId = normalizeTenantId(explicitTenantId)
      if (
        state.phase !== 'switching' ||
        tenantId !== state.pendingTenantId ||
        explicitSwitchId !== state.switchId
      ) {
        return stale('Workspace switch request is no longer current')
      }
      return Object.freeze({
        tenantId,
        epoch: state.epoch,
        phase: state.phase,
        mode,
        switchId: explicitSwitchId,
      })
    }

    return Object.freeze({
      tenantId:
        mode === 'bootstrap'
          ? normalizeTenantId(explicitTenantId) || state.activeTenantId
          : normalizeTenantId(explicitTenantId),
      epoch: state.epoch,
      phase: state.phase,
      mode,
    })
  }

  const assertConsumable = (
    snapshot: WorkspaceRequestSnapshot | undefined,
    responseTenantId = ''
  ) => {
    if (!snapshot || snapshot.mode === 'none') return
    if (snapshot.epoch !== state.epoch) {
      return stale('Workspace request epoch is stale')
    }
    if (snapshot.mode === 'normal') {
      if (
        snapshot.phase !== 'ready' ||
        state.phase !== 'ready' ||
        snapshot.tenantId !== state.activeTenantId
      ) {
        return stale('Workspace request is no longer consumable')
      }
    } else if (snapshot.mode === 'bootstrap') {
      if (state.phase !== 'bootstrapping') {
        return stale('Workspace bootstrap request is no longer current')
      }
    } else if (
      snapshot.mode === 'switch' &&
      (state.phase !== 'switching' ||
        snapshot.switchId !== state.switchId ||
        snapshot.tenantId !== state.pendingTenantId)
    ) {
      return stale('Workspace switch response is no longer current')
    }

    const normalizedResponseTenantId = normalizeTenantId(responseTenantId)
    if (
      snapshot.mode !== 'bootstrap' &&
      snapshot.tenantId &&
      normalizedResponseTenantId &&
      normalizedResponseTenantId !== snapshot.tenantId
    ) {
      return stale('Workspace response tenant does not match the request')
    }
  }

  const clear = () => {
    state.activeTenantId = ''
    state.pendingTenantId = ''
    state.phase = 'bootstrapping'
    state.epoch += 1
    storage.removeItem(WORKSPACE_TENANT_STORAGE_KEY)
  }

  restore()

  return {
    state,
    restore,
    beginSwitch,
    isCurrentSwitch,
    commitSwitch,
    finishSwitch,
    rollbackSwitch,
    completeBootstrap,
    clearActiveTenant,
    captureRequest,
    assertConsumable,
    clear,
  }
}

export type WorkspaceContextCore = ReturnType<typeof createWorkspaceContextCore>
