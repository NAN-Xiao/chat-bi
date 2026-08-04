import { computed, reactive } from 'vue'

import { useCache } from '@/utils/useCache'
import {
  createWorkspaceContextCore,
  type WorkspaceContextState,
  type WorkspaceContextStorage,
} from '@/utils/workspaceContextCore'

const { wsCache: localCache } = useCache()
const { wsCache: sessionCache } = useCache('sessionStorage')

const workspaceStorage: WorkspaceContextStorage = {
  getItem: (key) => {
    const value = sessionCache.get(key)
    return value === undefined || value === null ? null : String(value)
  },
  setItem: (key, value) => sessionCache.set(key, value),
  removeItem: (key) => sessionCache.delete(key),
}

const initialState = reactive<WorkspaceContextState>({
  activeTenantId: '',
  pendingTenantId: '',
  phase: 'bootstrapping',
  epoch: 0,
  switchId: 0,
})

export const workspaceContext = createWorkspaceContextCore(workspaceStorage, initialState)
export const workspaceContextState = initialState
export const isWorkspaceReady = computed(() => workspaceContextState.phase === 'ready')
export const isWorkspaceSwitching = computed(() => workspaceContextState.phase === 'switching')

const legacyWorkspaceKeys = [
  'user.tenantId',
  'user.tenantPublicId',
  'user.tenantName',
  'user.tenantRole',
  'user.workspaceRole',
  'user.hasWorkspace',
  'user.workspaceStatus',
]

export const clearLegacyWorkspaceLocalState = () => {
  legacyWorkspaceKeys.forEach((key) => localCache.delete(key))
}

clearLegacyWorkspaceLocalState()
