import { defineStore } from 'pinia'
// import { ref } from 'vue'
import { AuthApi } from '@/api/login'
import { tenantApi, type TenantInfo } from '@/api/tenant'
import { useCache } from '@/utils/useCache'
import { i18n } from '@/i18n'
import { store } from './index'
import { getCurrentRouter, getQueryString, getZhishuAddr, isPlatform } from '@/utils/utils'
import {
  clearPlatformWorkspaceDelegateContext,
  isPlatformWorkspaceDelegateSession,
  setPlatformWorkspaceDelegateContext,
  type PlatformWorkspaceDelegateTenant,
} from '@/utils/platformWorkspaceDelegate'

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
      return ['owner', 'admin'].includes(String(this.workspaceRole || this.tenantRole || '').trim().toLowerCase())
    },
    isTenantOwnerUser(): boolean {
      return String(this.workspaceRole || this.tenantRole || '').trim().toLowerCase() === 'owner'
    },
    isTenantMemberUser(): boolean {
      return String(this.workspaceRole || this.tenantRole || '').trim().toLowerCase() === 'member'
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
      this.setToken(res.access_token)
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
        let logout_url = getZhishuAddr() + '#/login'
        if (currentPath) {
          logout_url += `?redirect=${currentPath}`
        }
        window.location.href = logout_url
        window.open(res, logout_url)
        return logout_url
      }
      return null
    },

    async info() {
      const res: any = await AuthApi.info()
      const res_data = res || {}

      const keys = [
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
      ] as const

      keys.forEach((key) => {
        const dkey =
          key === 'uid' ? 'id' : key === 'systemRole' ? 'system_role' : key === 'isSystemAdmin' ? 'isAdmin' : key
        const tenantKeyMap: Record<string, string> = {
          tenantId: 'tenant_id',
          tenantPublicId: 'tenant_public_id',
          tenantName: 'tenant_name',
          tenantRole: 'tenant_role',
          workspaceRole: 'workspace_role',
          hasWorkspace: 'has_workspace',
          workspaceStatus: 'workspace_status',
          globalRole: 'global_role',
        }
        const resolvedKey = tenantKeyMap[key] || dkey
        const rawValue = res_data[resolvedKey]
        const value = rawValue ?? ''
        if (key === 'exp' || key === 'time' || key === 'origin') {
          this[key] = Number(value)
        } else if (key === 'isSystemAdmin' || key === 'hasWorkspace') {
          this[key] = Boolean(value)
        } else {
          this[key] = String(value)
        }
        wsCache.set('user.' + key, value)
      })

      this.setLanguage(this.language)
      this.platformInfo = wsCache.get('user.platformInfo')
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
          return this.tenants
        }
        if (this.isSystemAdminUser) {
          this.setTenant(null)
        } else if (!this.tenantId && this.tenants.length > 0) {
          this.setTenant(this.tenants[0])
        } else if (this.tenantId && !this.tenants.some((tenant) => String(tenant.id) === String(this.tenantId))) {
          this.setTenant(null)
        }
        return this.tenants
      } finally {
        this.tenantLoading = false
      }
    },
    async switchTenant(tenantId: string | number): Promise<void> {
      const nextTenantId = String(tenantId || '')
      if (!nextTenantId || nextTenantId === String(this.tenantId || '')) {
        return
      }
      const previousTenant: TenantInfo = {
        id: this.tenantId,
        public_id: this.tenantPublicId,
        name: this.tenantName,
        role: this.tenantRole,
      }
      const targetTenant =
        this.tenants.find((tenant) => String(tenant.id) === nextTenantId) || ({
          id: nextTenantId,
          name: '',
          role: '',
        } as TenantInfo)
      this.setTenant(targetTenant)
      try {
        if (this.token || wsCache.get('user.token')) {
          await this.info()
          await this.loadTenants(true)
        }
      } catch (error) {
        this.setTenant(previousTenant)
        throw error
      }
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
      wsCache.set('user.tenantId', tenantId)
      wsCache.set('user.tenantPublicId', tenantPublicId)
      wsCache.set('user.tenantName', tenantName)
      wsCache.set('user.tenantRole', tenantRole)
      wsCache.set('user.workspaceRole', tenantRole)
      wsCache.set('user.hasWorkspace', this.hasWorkspace)
      wsCache.set('user.workspaceStatus', this.workspaceStatus)
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
