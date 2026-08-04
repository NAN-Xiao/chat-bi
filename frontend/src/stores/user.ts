import { defineStore } from 'pinia'
// import { ref } from 'vue'
import { AuthApi } from '@/api/login'
import { tenantApi, type TenantInfo } from '@/api/tenant'
import type { FullRequestConfig } from '@/utils/request'
import { useCache } from '@/utils/useCache'
import { i18n } from '@/i18n'
import { store } from './index'
import { getCurrentRouter, getQueryString, getShuzhiAddr, isPlatform } from '@/utils/utils'
import {
  clearPlatformWorkspaceDelegateContext,
  isPlatformWorkspaceDelegateSession,
  setPlatformWorkspaceDelegateContext,
  type PlatformWorkspaceDelegateTenant,
} from '@/utils/platformWorkspaceDelegate'
import {
  canManageCurrentWorkspace,
  normalizeWorkspaceRole,
} from '@/utils/workspacePermission'
import { workspaceContext, workspaceContextState } from '@/utils/workspaceContext'
import { clearWorkspaceSelectorCaches } from '@/utils/requestDedupe'
import { emitWorkspaceContextChange, useEmitt } from '@/utils/useEmitt'

const { wsCache } = useCache()

interface UserState {
  token: string
  uid: string
  account: string
  name: string
  language: string
  exp: number
  time: number
  origin: number
  systemRole: string
  globalRole: string
  isSystemAdmin: boolean
  tenantId: string
  tenantPublicId: string
  tenantName: string
  tenantRole: string
  workspaceRole: string
  hasWorkspace: boolean
  workspaceStatus: string
  tenants: TenantInfo[]
  tenantLoading: boolean
  platformInfo: any | null
  [key: string]: string | number | any | null
}

interface UserInfoDto extends Record<string, unknown> {
  id?: string | number
  tenant_id?: string | number
}

interface WorkspaceStoreSnapshot {
  tenantId: string
  tenantPublicId: string
  tenantName: string
  tenantRole: string
  workspaceRole: string
  hasWorkspace: boolean
  workspaceStatus: string
  datasourceId?: number
}

const captureWorkspaceStoreSnapshot = (
  user: UserState,
  datasourceId?: number
): WorkspaceStoreSnapshot => ({
  tenantId: user.tenantId,
  tenantPublicId: user.tenantPublicId,
  tenantName: user.tenantName,
  tenantRole: user.tenantRole,
  workspaceRole: user.workspaceRole,
  hasWorkspace: user.hasWorkspace,
  workspaceStatus: user.workspaceStatus,
  datasourceId,
})

const restoreWorkspaceStoreSnapshot = (
  user: UserState,
  snapshot: WorkspaceStoreSnapshot
) => {
  user.tenantId = snapshot.tenantId
  user.tenantPublicId = snapshot.tenantPublicId
  user.tenantName = snapshot.tenantName
  user.tenantRole = snapshot.tenantRole
  user.workspaceRole = snapshot.workspaceRole
  user.hasWorkspace = snapshot.hasWorkspace
  user.workspaceStatus = snapshot.workspaceStatus
}

const assertUserInfoTenant = (userInfo: UserInfoDto, expectedTenantId: string) => {
  const responseTenantId = String(userInfo.tenant_id || '')
  if (responseTenantId !== expectedTenantId) {
    throw new Error('目标工作空间校验失败，请刷新后重试')
  }
}

const emitWorkspaceChanged = (tenantId: string) => {
  useEmitt().emitter.emit('datasource-context-change', null)
  emitWorkspaceContextChange({ tenantId, phase: 'changed' })
}

export const UserStore = defineStore('user', {
  state: (): UserState => {
    return {
      token: '',
      uid: '',
      account: '',
      name: '',
      language: 'zh-CN',
      exp: 0,
      time: 0,
      origin: 0,
      systemRole: 'viewer',
      globalRole: 'normal_user',
      isSystemAdmin: false,
      tenantId: '',
      tenantPublicId: '',
      tenantName: '',
      tenantRole: '',
      workspaceRole: '',
      hasWorkspace: false,
      workspaceStatus: 'workspace_required',
      tenants: [],
      tenantLoading: false,
      platformInfo: null,
    }
  },
  getters: {
    getToken(): string {
      return this.token
    },
    getUid(): string {
      return this.uid
    },
    getAccount(): string {
      return this.account
    },
    getName(): string {
      return this.name
    },
    getLanguage(): string {
      return this.language
    },
    getExp(): number {
      return this.exp
    },
    getTime(): number {
      return this.time
    },
    isSystemAdminUser(): boolean {
      return (
        this.globalRole === 'platform_admin' ||
        ['system_admin', 'collab_admin'].includes(String(this.systemRole || '').trim().toLowerCase())
      )
    },
    isPlatformWorkspaceDelegate(): boolean {
      return this.workspaceStatus === 'platform_workspace_delegate'
    },
    isSuperAdminUser(): boolean {
      return String(this.systemRole || '').trim().toLowerCase() === 'system_admin'
    },
    isCollabAdminUser(): boolean {
      return this.systemRole === 'collab_admin'
    },
    isTenantAdminUser(): boolean {
      return canManageCurrentWorkspace(this)
    },
    isTenantOwnerUser(): boolean {
      return normalizeWorkspaceRole(this.workspaceRole || this.tenantRole) === 'owner'
    },
    isTenantMemberUser(): boolean {
      return normalizeWorkspaceRole(this.workspaceRole || this.tenantRole) === 'member'
    },
    isSystemManagerUser(): boolean {
      return (
        this.isSystemAdmin ||
        this.isSystemAdminUser ||
        this.isCollabAdminUser ||
        this.isTenantAdminUser
      )
    },
    isAdmin(): boolean {
      return this.isSystemManagerUser
    },
    getOrigin(): number {
      return this.origin
    },
    getPlatformInfo(): any | null {
      return this.platformInfo
    },
    getTenantId(): string {
      return this.tenantId
    },
    getTenantPublicId(): string {
      return this.tenantPublicId
    },
    getTenantName(): string {
      return this.tenantName || this.tenantPublicId || this.tenantId
    },
    getTenantRole(): string {
      return this.workspaceRole || this.tenantRole
    },
    getGlobalRole(): string {
      return this.globalRole
    },
    getWorkspaceStatus(): string {
      return this.workspaceStatus
    },
    hasActiveWorkspace(): boolean {
      if (this.isPlatformWorkspaceDelegate) return !!this.tenantId
      if (this.isSystemAdminUser || !this.tenantId) return false
      if (this.workspaceStatus && this.workspaceStatus !== 'active') return false
      return this.hasWorkspace || !!this.tenantId
    },
    getTenants(): TenantInfo[] {
      return this.tenants
    },
  },
  actions: {
    async login(formData: { username: string; password: string }) {
      const res: any = await AuthApi.login(formData)
      this.startAuthenticatedSession(res.access_token)
    },

    startAuthenticatedSession(token: string) {
      this.clear()
      this.setToken(token)
    },

    async logout() {
      let param = { token: this.token }
      if (wsCache.get('user.platformInfo')) {
        param = { ...param, ...wsCache.get('user.platformInfo') }
      }
      const res: any = await AuthApi.logout(param)
      this.clear()
      if (res) {
        window.location.href = res
        window.open(res, '_self')
        return res
      }
      if (
        (getQueryString('code') && getQueryString('state')?.includes('oauth2_state')) ||
        isPlatform()
      ) {
        const currentPath = getCurrentRouter()
        let logout_url = getShuzhiAddr() + '#/login'
        if (currentPath) {
          logout_url += `?redirect=${currentPath}`
        }
        window.location.href = logout_url
        window.open(res, logout_url)
        return logout_url
      }
      return null
    },

    async requestInfo(config?: FullRequestConfig): Promise<UserInfoDto> {
      const res = await AuthApi.info(config)
      return (res || {}) as UserInfoDto
    },
    applyInfo(res: UserInfoDto) {
      const identityValues = {
        uid: String(res.id ?? ''),
        account: String(res.account ?? ''),
        name: String(res.name ?? ''),
        language: String(res.language ?? ''),
        exp: Number(res.exp ?? 0),
        time: Number(res.time ?? 0),
        origin: Number(res.origin ?? 0),
        systemRole: String(res.system_role ?? ''),
        globalRole: String(res.global_role ?? ''),
        isSystemAdmin: Boolean(res.isAdmin),
      }
      Object.assign(this, identityValues)
      Object.entries(identityValues).forEach(([key, value]) => {
        wsCache.set(`user.${key}`, value)
      })

      this.tenantId = String(res.tenant_id ?? '')
      this.tenantPublicId = String(res.tenant_public_id ?? '')
      this.tenantName = String(res.tenant_name ?? '')
      this.tenantRole = String(res.tenant_role ?? '')
      this.workspaceRole = String(res.workspace_role ?? res.tenant_role ?? '')
      this.hasWorkspace = Boolean(res.has_workspace)
      this.workspaceStatus = String(res.workspace_status ?? 'workspace_required')
      this.setLanguage(this.language)
      this.platformInfo = wsCache.get('user.platformInfo')
    },
    async info() {
      const delegateSession = isPlatformWorkspaceDelegateSession()
      const bootstrapping = workspaceContextState.phase === 'bootstrapping'
      const workspaceMode = delegateSession ? 'none' : bootstrapping ? 'bootstrap' : 'normal'
      const res = await this.requestInfo({ requestOptions: { workspaceMode } })
      const serverTenantId = String(res.tenant_id || '')

      if (!delegateSession && (bootstrapping || String(res.workspace_status || '') === 'platform_admin')) {
        const resolution = workspaceContext.completeBootstrap(serverTenantId)
        if (resolution.replaced) {
          ElMessage.warning('当前标签页保存的工作空间已不可用，已切换到可访问的工作空间')
        }
      } else if (delegateSession && bootstrapping) {
        workspaceContext.completeBootstrap(workspaceContextState.activeTenantId)
      }
      this.applyInfo(res)
    },
    async loadTenants(force = false): Promise<TenantInfo[]> {
      if (this.tenantLoading) {
        return this.tenants
      }
      if (!force && this.tenants.length > 0) {
        return this.tenants
      }
      this.tenantLoading = true
      try {
        const res = await tenantApi.list()
        this.tenants = Array.isArray(res) ? res : []
        if (this.isPlatformWorkspaceDelegate) {
          const currentTenant = this.tenants.find(
            (tenant) => String(tenant.id) === String(this.tenantId || '')
          )
          this.tenants = this.tenantId
            ? [
                {
                  id: this.tenantId,
                  public_id: this.tenantPublicId,
                  name: this.tenantName || this.tenantPublicId || this.tenantId,
                  role: this.getTenantRole || 'owner',
                  ...currentTenant,
                },
              ]
            : []
          return this.tenants
        }
        return this.tenants
      } finally {
        this.tenantLoading = false
      }
    },
    async switchTenant(tenantId: string | number): Promise<boolean> {
      const transaction = workspaceContext.beginSwitch(String(tenantId || ''))
      if (!transaction) return false

      const { useDatasourceContextStore } = await import('./datasourceContext')
      if (!workspaceContext.isCurrentSwitch(transaction)) return false
      const datasourceContext = useDatasourceContextStore()
      const previous = captureWorkspaceStoreSnapshot(this, datasourceContext.datasourceId)

      emitWorkspaceContextChange({ tenantId: transaction.targetTenantId, phase: 'changing' })
      clearWorkspaceSelectorCaches()
      datasourceContext.clear(false)

      try {
        const userInfo = await this.requestInfo({
          requestOptions: {
            workspaceMode: 'switch',
            workspaceTenantId: transaction.targetTenantId,
            workspaceSwitchId: transaction.switchId,
          },
        })
        assertUserInfoTenant(userInfo, transaction.targetTenantId)
        if (!workspaceContext.commitSwitch(transaction)) return false
        this.applyInfo(userInfo)
        await datasourceContext.loadDatasources(true, {
          tenantId: transaction.targetTenantId,
          workspaceSwitchId: transaction.switchId,
        })
        if (!workspaceContext.finishSwitch(transaction)) return false
        emitWorkspaceChanged(transaction.targetTenantId)
        return true
      } catch (error) {
        if (!workspaceContext.isCurrentSwitch(transaction)) return false
        restoreWorkspaceStoreSnapshot(this, previous)
        workspaceContext.rollbackSwitch(transaction)
        try {
          await datasourceContext.loadDatasources(true)
          datasourceContext.setDatasourceById(previous.datasourceId, false)
        } catch (restoreError) {
          console.warn('Failed to restore datasource after workspace switch', restoreError)
        }
        emitWorkspaceChanged(previous.tenantId)
        throw error
      }
    },
    async clearActiveTenant(): Promise<void> {
      const { useDatasourceContextStore } = await import('./datasourceContext')
      emitWorkspaceContextChange({ tenantId: '', phase: 'changing' })
      clearWorkspaceSelectorCaches()
      workspaceContext.clearActiveTenant()
      this.setTenant(null)
      useDatasourceContextStore().clear(false)
      emitWorkspaceChanged('')
    },
    setTenant(tenant: Partial<TenantInfo> | null) {
      const tenantId = tenant?.id ? String(tenant.id) : ''
      const tenantPublicId = tenant?.public_id ? String(tenant.public_id) : ''
      const tenantName = tenant?.name ? String(tenant.name) : ''
      const tenantRole = tenant?.role ? String(tenant.role) : ''
      this.tenantId = tenantId
      this.tenantPublicId = tenantPublicId
      this.tenantName = tenantName
      this.tenantRole = tenantRole
      this.workspaceRole = tenantRole
      this.hasWorkspace = (this.isPlatformWorkspaceDelegate || !this.isSystemAdminUser) && !!tenantId
      this.workspaceStatus = this.isPlatformWorkspaceDelegate
        ? 'platform_workspace_delegate'
        : this.isSystemAdminUser
          ? 'platform_admin'
          : tenantId
            ? 'active'
            : 'workspace_required'
    },
    async enterPlatformWorkspaceDelegate(tenant: PlatformWorkspaceDelegateTenant): Promise<void> {
      if (!setPlatformWorkspaceDelegateContext(tenant)) return
      this.tenantId = String(tenant.id || '')
      this.tenantPublicId = tenant.public_id ? String(tenant.public_id) : ''
      this.tenantName = tenant.name ? String(tenant.name) : ''
      this.tenantRole = 'owner'
      this.workspaceRole = 'owner'
      this.hasWorkspace = true
      this.workspaceStatus = 'platform_workspace_delegate'
      if (this.token || wsCache.get('user.token')) {
        await this.info()
      }
    },
    async exitPlatformWorkspaceDelegate(): Promise<void> {
      if (!this.isPlatformWorkspaceDelegate && !isPlatformWorkspaceDelegateSession()) return
      clearPlatformWorkspaceDelegateContext()
      this.workspaceStatus = 'platform_admin'
      this.workspaceRole = ''
      this.tenantRole = ''
      this.hasWorkspace = false
      if (this.token || wsCache.get('user.token')) {
        await this.info()
      }
    },
    setToken(token: string) {
      wsCache.set('user.token', token)
      this.token = token
    },
    setExp(exp: number) {
      wsCache.set('user.exp', exp)
      this.exp = exp
    },
    setTime(time: number) {
      wsCache.set('user.time', time)
      this.time = time
    },
    setUid(uid: string) {
      wsCache.set('user.uid', uid)
      this.uid = uid
    },
    setAccount(account: string) {
      wsCache.set('user.account', account)
      this.account = account
    },
    setName(name: string) {
      wsCache.set('user.name', name)
      this.name = name
    },
    setLanguage(language: string) {
      if (!language) {
        language = 'zh-CN'
      } else if (language === 'zh_CN') {
        language = 'zh-CN'
      } else if (language === 'zh_TW') {
        language = 'zh-TW'
      } else if (language === 'ko_KR') {
        language = 'ko-KR'
      }
      wsCache.set('user.language', language)
      this.language = language
      i18n.global.locale.value = language
      /* const { locale } = useI18n()
      locale.value = language */
      // locale.setLang(language)
    },
    setOrigin(origin: number) {
      wsCache.set('user.origin', origin)
      this.origin = origin
    },
    setPlatformInfo(info: any | null) {
      wsCache.set('user.platformInfo', info)
      this.platformInfo = info
    },
    clear() {
      clearPlatformWorkspaceDelegateContext()
      workspaceContext.clear()
      clearWorkspaceSelectorCaches()
      const keys: string[] = [
        'token',
        'uid',
        'account',
        'name',
        'language',
        'exp',
        'time',
        'origin',
        'systemRole',
        'globalRole',
        'isSystemAdmin',
        'tenantId',
        'tenantPublicId',
        'tenantName',
        'tenantRole',
        'workspaceRole',
        'hasWorkspace',
        'workspaceStatus',
        'platformInfo',
      ]
      keys.forEach((key) => wsCache.delete('user.' + key))
      this.$reset()
    },
  },
})

export const useUserStore = () => {
  return UserStore(store)
}
