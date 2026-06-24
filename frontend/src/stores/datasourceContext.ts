import { defineStore } from 'pinia'
import { datasourceApi } from '@/api/datasource'
import { useCache } from '@/utils/useCache'
import { store } from './index'
import { useUserStore } from './user'

const { wsCache } = useCache()

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
    cacheKey() {
      const userStore = useUserStore()
      return `datasource.current.${userStore.getUid || 'default'}.${userStore.getTenantId || 'default'}`
    },

    legacyCacheKey() {
      const userStore = useUserStore()
      return `analysisAssistant.datasource.${userStore.getUid || 'default'}`
    },

    async loadDatasources(force = false) {
      const userStore = useUserStore()
      const requestTenantId = userStore.getTenantId || 'default'
      if (this.tenantScopeId && this.tenantScopeId !== requestTenantId) {
        this.clear(false)
      }
      if (
        (this.loading && !force) ||
        (this.initialized && !force && this.tenantScopeId === requestTenantId)
      ) {
        return
      }
      this.loading = true
      try {
        const res = await datasourceApi.accessibleList()
        if ((useUserStore().getTenantId || 'default') !== requestTenantId) {
          return
        }
        this.datasources = Array.isArray(res) ? res : []
        const tenantScopedCachedId = wsCache.get(this.cacheKey())
        const legacyCachedId = userStore.getTenantId ? undefined : wsCache.get(this.legacyCacheKey())
        const cachedId = Number(tenantScopedCachedId || legacyCachedId)
        const currentDatasource = this.datasourceId
          ? this.datasources.find((item) => Number(item.id) === Number(this.datasourceId))
          : undefined
        const datasource =
          currentDatasource ||
          this.datasources.find((item) => Number(item.id) === cachedId) ||
          this.datasources[0]
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
      } finally {
        this.loading = false
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
        wsCache.delete(this.legacyCacheKey())
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
      this.initialized = false
      if (persist) {
        wsCache.delete(this.cacheKey())
        wsCache.delete(this.legacyCacheKey())
      }
    },
  },
})

export const useDatasourceContextStore = () => DatasourceContextStore(store)
