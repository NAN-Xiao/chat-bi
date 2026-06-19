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
    loading: false,
    initialized: false,
  }),

  actions: {
    cacheKey() {
      const userStore = useUserStore()
      return `datasource.current.${userStore.getUid || 'default'}`
    },

    legacyCacheKey() {
      const userStore = useUserStore()
      return `analysisAssistant.datasource.${userStore.getUid || 'default'}`
    },

    async loadDatasources(force = false) {
      if (this.loading || (this.initialized && !force)) {
        return
      }
      this.loading = true
      try {
        const res = await datasourceApi.list()
        this.datasources = Array.isArray(res) ? res : []
        const cachedId = Number(wsCache.get(this.cacheKey()) || wsCache.get(this.legacyCacheKey()))
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

    clear(persist = true) {
      this.datasourceId = undefined
      this.datasourceName = ''
      this.datasourceType = ''
      this.datasourceTypeName = ''
      this.projectRole = ''
      this.canCreateDashboard = false
      this.canManageDashboard = false
      this.canManageProject = false
      if (persist) {
        wsCache.delete(this.cacheKey())
        wsCache.delete(this.legacyCacheKey())
      }
    },

    resetForUserChange() {
      this.datasources = []
      this.initialized = false
      this.loading = false
      this.clear(false)
    },
  },
})

export const useDatasourceContextStore = () => DatasourceContextStore(store)
