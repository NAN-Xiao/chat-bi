import { defineStore } from 'pinia'
import { datasourceApi } from '@/api/datasource'
import { useCache } from '@/utils/useCache'
import { store } from './index'
import { useUserStore } from './user'
import { workspaceContext, workspaceContextState } from '@/utils/workspaceContext'
import { isPlatformWorkspaceDelegateSession } from '@/utils/platformWorkspaceDelegate'

const { wsCache } = useCache()
let datasourceLoadPromise: Promise<void> | null = null
let datasourceLoadTenantId = ''
let datasourceLoadSwitchId: number | undefined

interface DatasourceLoadOptions {
  tenantId?: string
  workspaceSwitchId?: number
}

export interface DatasourceContextItem {
  id?: number | string
  name: string
  type?: string
  type_name?: string
  project_role?: string
  can_create_dashboard?: boolean
  can_manage_dashboard?: boolean
  can_manage_project?: boolean
}

interface DatasourceContextState {
  datasources: DatasourceContextItem[]
  datasourceId?: number
  datasourceName: string
  datasourceType: string
  datasourceTypeName: string
  projectRole: string
  canCreateDashboard: boolean
  canManageDashboard: boolean
  canManageProject: boolean
  tenantScopeId: string
  loading: boolean
  initialized: boolean
}

export const DatasourceContextStore = defineStore('datasourceContext', {
  state: (): DatasourceContextState => ({
    datasources: [],
    datasourceId: undefined,
    datasourceName: '',
    datasourceType: '',
    datasourceTypeName: '',
    projectRole: '',
    canCreateDashboard: false,
    canManageDashboard: false,
    canManageProject: false,
    tenantScopeId: '',
    loading: false,
    initialized: false,
  }),

  actions: {
    cacheKey(tenantId?: string) {
      const userStore = useUserStore()
      return `datasource.current.${userStore.getUid || 'default'}.${tenantId || userStore.getTenantId || 'default'}`
    },

    async loadDatasources(force = false, options?: DatasourceLoadOptions) {
      const userStore = useUserStore()
      const requestTenantId = options?.tenantId || userStore.getTenantId || 'default'
      if (this.tenantScopeId && this.tenantScopeId !== requestTenantId) {
        this.clear(false)
      }
      if (
        this.loading &&
        datasourceLoadPromise &&
        datasourceLoadTenantId === requestTenantId &&
        datasourceLoadSwitchId === options?.workspaceSwitchId
      ) {
        return datasourceLoadPromise
      }
      if (
        (this.initialized && !force && this.tenantScopeId === requestTenantId)
      ) {
        return
      }
      this.loading = true
      const loadPromise = (async () => {
        const res = await datasourceApi.accessibleList({
          requestOptions: options?.workspaceSwitchId
            ? {
                workspaceMode: 'switch',
                customError: true,
                workspaceTenantId: requestTenantId,
                workspaceSwitchId: options?.workspaceSwitchId,
              }
            : undefined,
        })
        const switchIsCurrent = options?.workspaceSwitchId
          ? workspaceContext.isCurrentSwitch(requestTenantId, options.workspaceSwitchId)
          : isPlatformWorkspaceDelegateSession() ||
            (workspaceContextState.phase === 'ready' &&
              workspaceContextState.activeTenantId ===
                (requestTenantId === 'default' ? '' : requestTenantId))
        if (!switchIsCurrent || (useUserStore().getTenantId || 'default') !== requestTenantId) {
          return
        }
        this.datasources = Array.isArray(res) ? res : []
        const tenantScopedCachedId = wsCache.get(this.cacheKey(requestTenantId))
        const cachedId = tenantScopedCachedId === undefined || tenantScopedCachedId === null
          ? undefined
          : Number(tenantScopedCachedId)
        const currentDatasource = this.datasourceId
          ? this.datasources.find((item) => Number(item.id) === Number(this.datasourceId))
          : undefined
        const datasource =
          currentDatasource ||
          (cachedId === undefined
            ? undefined
            : this.datasources.find((item) => Number(item.id) === cachedId))
        if (datasource) {
          this.setDatasource(
            Number(datasource.id),
            datasource.name,
            datasource.type || '',
            datasource.type_name || '',
            datasource.project_role || '',
            datasource.can_create_dashboard === true,
            datasource.can_manage_dashboard === true,
            datasource.can_manage_project === true,
            false
          )
        } else {
          this.clear(false)
        }
        this.tenantScopeId = requestTenantId
        this.initialized = true
      })()
      datasourceLoadPromise = loadPromise
      datasourceLoadTenantId = requestTenantId
      datasourceLoadSwitchId = options?.workspaceSwitchId
      try {
        return await loadPromise
      } finally {
        if (datasourceLoadPromise === loadPromise) {
          datasourceLoadPromise = null
          datasourceLoadTenantId = ''
          datasourceLoadSwitchId = undefined
          this.loading = false
        }
      }
    },

    setDatasource(
      id?: number,
      name = '',
      type = '',
      typeName = '',
      projectRole = '',
      canCreateDashboard = false,
      canManageDashboard = false,
      canManageProject = false,
      persist = true
    ) {
      this.datasourceId = id
      this.datasourceName = name
      this.datasourceType = type
      this.datasourceTypeName = typeName
      this.projectRole = projectRole
      this.canCreateDashboard = canCreateDashboard
      this.canManageDashboard = canManageDashboard
      this.canManageProject = canManageProject
      if (persist && id) {
        wsCache.set(this.cacheKey(), id)
      }
    },

    setDatasourceById(id?: number | string, persist = false) {
      if (!id) return false
      const datasource = this.datasources.find((item) => String(item.id) === String(id))
      if (!datasource) return false
      this.setDatasource(
        Number(datasource.id),
        datasource.name,
        datasource.type || '',
        datasource.type_name || '',
        datasource.project_role || '',
        datasource.can_create_dashboard === true,
        datasource.can_manage_dashboard === true,
        datasource.can_manage_project === true,
        persist
      )
      return true
    },

    async activateDatasourceById(id?: number | string, persist = false) {
      if (!id) return false
      if (!this.datasources.length) {
        await this.loadDatasources()
      }
      return this.setDatasourceById(id, persist)
    },

    clear(persist = true) {
      datasourceLoadPromise = null
      datasourceLoadTenantId = ''
      datasourceLoadSwitchId = undefined
      this.datasources = []
      this.datasourceId = undefined
      this.datasourceName = ''
      this.datasourceType = ''
      this.datasourceTypeName = ''
      this.projectRole = ''
      this.canCreateDashboard = false
      this.canManageDashboard = false
      this.canManageProject = false
      this.tenantScopeId = ''
      this.loading = false
      this.initialized = false
      if (persist) {
        wsCache.delete(this.cacheKey())
      }
    },
  },
})

export const useDatasourceContextStore = () => DatasourceContextStore(store)
