// src/services/request.ts
import axios, {
  AxiosError,
  type AxiosInstance,
  type AxiosRequestConfig,
  type AxiosResponse,
  type InternalAxiosRequestConfig,
  type CancelTokenSource,
} from 'axios'

import { useCache } from '@/utils/useCache'
import { getLocale, toLoginPage } from './utils'
import { useAssistantStore } from '@/stores/assistant'
import JSONBig from 'json-bigint'
import {
  assertPlatformWorkspaceDelegateSnapshot,
  capturePlatformWorkspaceDelegateSnapshot,
  clearPlatformWorkspaceDelegateContext,
  PLATFORM_WORKSPACE_DELEGATE_HEADER,
} from '@/utils/platformWorkspaceDelegate'
import type { PlatformWorkspaceDelegateRequestSnapshot } from '@/utils/platformWorkspaceDelegateCore'
import { workspaceContext } from '@/utils/workspaceContext'
import { clearWorkspaceSelectorCaches } from '@/utils/requestDedupe'
import {
  isWorkspaceContextStaleError,
  type WorkspaceRequestMode,
  type WorkspaceRequestSnapshot,
} from '@/utils/workspaceContextCore'
// import { i18n } from '@/i18n'
// const t = i18n.global.t
const assistantStore = useAssistantStore()
const { wsCache } = useCache()
const TENANT_CONTEXT_HEADER = 'x-shuzhi-current-tenant-id'

const readHeader = (response: AxiosResponse, name: string) => {
  const headers = response.headers || {}
  return String(headers[name] || headers[name.toLowerCase()] || '').trim()
}

const HTML_ERROR_RESPONSE_PATTERN = /<\s*(?:!doctype|html|head|body|title|center|h[1-6])[\s>]/i
const MAX_ERROR_MESSAGE_LENGTH = 300
const DUPLICATE_ERROR_MESSAGE_INTERVAL = 2000
let lastErrorMessage = ''
let lastErrorMessageAt = 0

const normalizeErrorText = (value: string) => {
  const text = value.trim()
  if (!text || HTML_ERROR_RESPONSE_PATTERN.test(text)) return ''
  const normalized = text.replace(/\s+/g, ' ')
  if (normalized.length <= MAX_ERROR_MESSAGE_LENGTH) return normalized
  return `${normalized.slice(0, MAX_ERROR_MESSAGE_LENGTH)}...`
}

const errorResponseMessage = (data: any) => {
  if (!data) return ''
  if (typeof data === 'string') return normalizeErrorText(data)
  if (typeof data?.detail === 'string') return normalizeErrorText(data.detail)
  if (typeof data?.message === 'string') return normalizeErrorText(data.message)
  if (typeof data?.msg === 'string') return normalizeErrorText(data.msg)
  try {
    return normalizeErrorText(JSON.stringify(data))
  } catch {
    return normalizeErrorText(String(data))
  }
}

const statusErrorMessage = (status?: number) => {
  switch (status) {
    case 400:
      return '请求参数不正确，请检查后重试'
    case 401:
      return '登录状态已失效，请重新登录'
    case 403:
      return '没有访问权限'
    case 404:
      return '请求资源不存在'
    case 500:
      return '服务异常，请稍后重试'
    case 502:
      return '服务网关异常（502），请稍后重试或联系管理员'
    case 503:
      return '服务暂时不可用（503），请稍后重试'
    case 504:
      return '服务响应超时（504），请稍后重试'
    default:
      return status ? '服务请求失败，请稍后重试' : ''
  }
}

export const formatRequestErrorMessage = (error: any, fallback = '请求失败，请稍后重试') => {
  if (!error) return fallback
  if (axios.isAxiosError(error)) {
    const responseMessage = error.response?.data ? errorResponseMessage(error.response.data) : ''
    return (
      responseMessage ||
      statusErrorMessage(error.response?.status) ||
      normalizeErrorText(error.message || '') ||
      fallback
    )
  }
  if (error?.response?.data) {
    const responseMessage = errorResponseMessage(error.response.data)
    if (responseMessage) return responseMessage
  }
  if (typeof error === 'string') {
    return normalizeErrorText(error) || fallback
  }
  return normalizeErrorText(error?.message || String(error)) || fallback
}

const showErrorMessage = (message: string) => {
  const now = Date.now()
  if (message === lastErrorMessage && now - lastErrorMessageAt < DUPLICATE_ERROR_MESSAGE_INTERVAL) {
    return
  }
  lastErrorMessage = message
  lastErrorMessageAt = now
  ElMessage({
    message,
    type: 'error',
    showClose: true,
  })
}

const pushAppRoute = async (route: any, fallbackHash: string) => {
  try {
    const { default: router } = await import('@/router')
    await router.push(route)
  } catch (error) {
    console.warn('Failed to route inside app', error)
    window.location.hash = fallbackHash
  }
}

const invalidateAuthenticationSession = () => {
  wsCache.delete('user.token')
  clearPlatformWorkspaceDelegateContext()
  workspaceContext.clear()
  clearWorkspaceSelectorCaches()
}

const clearUserStore = async () => {
  const { useUserStore } = await import('@/stores/user')
  useUserStore().clear()
}
// Response data structure
export interface ApiResponse<T = unknown> {
  code: number
  data: T
  message: string
  success: boolean
  [key: string]: any // Allow additional fields
}

// Extended request options
export interface RequestOptions {
  silent?: boolean // Silent mode (no error alerts)
  rawResponse?: boolean // Return raw Axios response
  customError?: boolean // Custom error handling
  retryCount?: number // Number of retry attempts
  workspaceMode?: WorkspaceRequestMode
  workspaceTenantId?: string
  workspaceSwitchId?: number
}

// Merged request configuration
export interface FullRequestConfig extends AxiosRequestConfig {
  requestOptions?: RequestOptions
  __workspaceSnapshot?: WorkspaceRequestSnapshot
  __platformDelegateSnapshot?: PlatformWorkspaceDelegateRequestSnapshot
}

const captureWorkspaceRequest = (
  options: RequestOptions = {},
  delegateSnapshot = capturePlatformWorkspaceDelegateSnapshot()
) => {
  const workspaceMode =
    assistantStore.getToken || delegateSnapshot.active
      ? 'none'
      : options.workspaceMode || 'normal'
  return workspaceContext.captureRequest(
    workspaceMode,
    options.workspaceTenantId,
    options.workspaceSwitchId
  )
}

const captureWorkspaceRequestConfig = (config: FullRequestConfig): FullRequestConfig => {
  const delegateSnapshot = capturePlatformWorkspaceDelegateSnapshot()
  const snapshot = captureWorkspaceRequest(config.requestOptions, delegateSnapshot)
  const headers: Record<string, any> = { ...(config.headers || {}) }
  if (delegateSnapshot.active) {
    headers['X-SHUZHI-TENANT-ID'] = delegateSnapshot.tenantId
    headers[PLATFORM_WORKSPACE_DELEGATE_HEADER] = '1'
  } else if (snapshot.tenantId && snapshot.mode !== 'none') {
    headers['X-SHUZHI-TENANT-ID'] = snapshot.tenantId
  }
  return {
    ...config,
    headers: headers as AxiosRequestConfig['headers'],
    __workspaceSnapshot: snapshot,
    __platformDelegateSnapshot: delegateSnapshot,
  }
}

const assertWorkspaceResponseConsumable = (
  config?: FullRequestConfig,
  response?: AxiosResponse
) => {
  const responseTenantId = response ? readHeader(response, TENANT_CONTEXT_HEADER) : ''
  assertPlatformWorkspaceDelegateSnapshot(config?.__platformDelegateSnapshot, responseTenantId)
  workspaceContext.assertConsumable(
    config?.__workspaceSnapshot,
    responseTenantId
  )
}

// Custom error type
export interface RequestError<T = any> extends Error {
  config: FullRequestConfig
  code?: string
  request?: any
  response?: AxiosResponse<T>
  isAxiosError: boolean
}

class HttpService {
  private instance: AxiosInstance
  private cancelTokenSource: CancelTokenSource

  constructor(config?: AxiosRequestConfig) {
    this.cancelTokenSource = axios.CancelToken.source()
    this.instance = axios.create({
      baseURL: import.meta.env.VITE_API_BASE_URL,
      timeout: 100000,
      headers: {
        'Content-Type': 'application/json',
        ...config?.headers,
      },
      // add transformResponse to bigint
      transformResponse: [
        function (data) {
          try {
            return JSONBig.parse(data) // use JSON-bigint
            // eslint-disable-next-line @typescript-eslint/no-unused-vars
          } catch (e) {
            try {
              return JSON.parse(data)
              // eslint-disable-next-line @typescript-eslint/no-unused-vars
            } catch (parseError) {
              return data
            }
          }
        },
      ],
      ...config,
    })

    this.setupInterceptors()
  }

  /* private cancelCurrentRequest(message: string) {
    this.cancelTokenSource.cancel(message)
    this.cancelTokenSource = axios.CancelToken.source()
  } */

  private setupInterceptors() {
    // Request interceptor
    this.instance.interceptors.request.use(
      async (config: InternalAxiosRequestConfig) => {
        // Add auth token
        const token = wsCache.get('user.token')
        if (token && config.headers) {
          config.headers['X-SHUZHI-TOKEN'] = `Bearer ${token}`
        }
        if (assistantStore.getToken) {
          const prefix = assistantStore.getType === 4 ? 'Embedded ' : 'Assistant '
          config.headers['X-SHUZHI-ASSISTANT-TOKEN'] = `${prefix}${assistantStore.getToken}`
          if (config.headers['X-SHUZHI-TOKEN']) config.headers.delete('X-SHUZHI-TOKEN')
          if (
            assistantStore.getType &&
            !!(assistantStore.getType % 2) &&
            assistantStore.getCertificate
          ) {
            if (
              /* (config.method?.toLowerCase() === 'get' && /\/chat\/\d+$/.test(config.url || '')) || */
              /^\/chat/.test(config.url || '') ||
              config.url?.includes('/system/assistant/ds')
            ) {
              await assistantStore.refreshCertificate(config.url || '')
            }
            config.headers['X-SHUZHI-ASSISTANT-CERTIFICATE'] = btoa(
              encodeURIComponent(assistantStore.getCertificate)
            )
          }
          if (!assistantStore.getType || assistantStore.getType === 2) {
            config.headers['X-SHUZHI-ASSISTANT-ONLINE'] = assistantStore.getOnline
          }
          if (assistantStore.getHostOrigin) {
            config.headers['X-SHUZHI-HOST-ORIGIN'] = assistantStore.getHostOrigin
          }
        }
        const locale = getLocale()
        if (locale) {
          /* const mapping = {
            'zh-CN': 'zh-CN',
            en: 'en-US',
            tw: 'zh-TW',
          } */
          /* const val = mapping[locale] || locale */
          config.headers['Accept-Language'] = locale
        }
        // Request logging
        // console.log(`[Request] ${config.method?.toUpperCase()} ${config.url}`)

        return config
      },
      (error) => {
        return Promise.reject(error)
      }
    )
    // Response interceptor
    this.instance.interceptors.response.use(
      (response: AxiosResponse) => {
        // console.log(`[Response] ${response.config.url}`, response.data)
        assertWorkspaceResponseConsumable(response.config, response)

        // Return raw response if configured
        if ((response.config as FullRequestConfig).requestOptions?.rawResponse) {
          return response
        }

        // Handle business logic
        /* if (response.data?.success !== true) {
          return Promise.reject(response.data)
        } */
        if (response.data?.code === 0) {
          return response.data.data
        } else if (response.data?.code) {
          return Promise.reject(response.data)
        }
        return response.data
      },
      async (error: AxiosError) => {
        const config = error.config as FullRequestConfig & { __retryCount?: number }
        const requestOptions = config?.requestOptions || {}

        try {
          assertWorkspaceResponseConsumable(config, error.response)
        } catch (workspaceError) {
          return Promise.reject(workspaceError)
        }
        if (isWorkspaceContextStaleError(error)) {
          return Promise.reject(error)
        }

        // Retry logic for specific status codes
        const shouldRetry =
          error.response?.status === 502 &&
          (config.__retryCount || 0) < (requestOptions.retryCount ?? 3)

        if (shouldRetry) {
          config.__retryCount = (config.__retryCount || 0) + 1

          // Exponential backoff
          await new Promise((resolve) => setTimeout(resolve, 1000 * (config.__retryCount || 1)))

          return this.instance.request(config)
        }

        // Unified error handling
        if (!requestOptions.customError && !requestOptions.silent) {
          this.handleError(error)
        }

        return Promise.reject(error)
      }
    )
  }

  private handleError(error: AxiosError) {
    if (isWorkspaceContextStaleError(error)) return
    let errorMessage = 'Request error'
    const hasUserToken = Boolean(wsCache.get('user.token'))

    if (error.response) {
      errorMessage = formatRequestErrorMessage(error, statusErrorMessage(error.response.status) || errorMessage)
      switch (error.response.status) {
        case 401:
          // Redirect to login page if needed
          invalidateAuthenticationSession()
          if (assistantStore.getAssistant) {
            clearUserStore()
              .catch((clearError) => {
                console.warn('Failed to clear user session after 401', clearError)
              })
              .finally(() => {
                pushAppRoute(
                  `/401?title=${encodeURIComponent(errorMessage)}`,
                  `/401?title=${encodeURIComponent(errorMessage)}`
                )
              })
            return
          }
          if (hasUserToken) {
            showErrorMessage(errorMessage)
          }
          setTimeout(() => {
            clearUserStore()
              .catch((clearError) => {
                console.warn('Failed to clear user session after 401', clearError)
              })
              .then(() => import('@/router'))
              .then(({ default: router }) => {
                const currentRoute = router.currentRoute.value
                return router.push(toLoginPage(currentRoute?.fullPath || ''))
              })
              .catch((routeError) => {
                console.warn('Failed to route to login inside app', routeError)
                window.location.hash = '/login'
              })
          }, 2000)
          return
        // break
      }
    } else if (error.request) {
      errorMessage = 'No response from server'
    } else if (axios.isCancel(error)) {
      errorMessage = 'Request canceled'
      return // Skip showing cancel messages
    } else {
      errorMessage = formatRequestErrorMessage(error, 'Unknown error')
    }

    // Show error using UI library (e.g., Element Plus, Ant Design)
    console.error(errorMessage)
    showErrorMessage(errorMessage)
  }

  // Cancel all pending requests
  public cancelRequests(message?: string) {
    this.cancelTokenSource.cancel(message)
    // Create new token source for future requests
    this.cancelTokenSource = axios.CancelToken.source()
  }

  // Base request method
  public request<T = any>(config: FullRequestConfig): Promise<T> {
    try {
      const capturedConfig = captureWorkspaceRequestConfig(config)
      return this.instance.request({
        cancelToken: this.cancelTokenSource.token,
        ...capturedConfig,
      })
    } catch (error) {
      return Promise.reject(error)
    }
  }

  // GET request
  public get<T = any>(url: string, config?: FullRequestConfig): Promise<T> {
    return this.request({ ...config, method: 'GET', url })
  }

  // POST request
  public post<T = any>(url: string, data?: any, config?: FullRequestConfig): Promise<T> {
    return this.request({ ...config, method: 'POST', url, data })
  }

  public async fetchStream(url: string, data?: any, controller?: AbortController): Promise<any> {
    const delegateSnapshot = capturePlatformWorkspaceDelegateSnapshot()
    const workspaceSnapshot = captureWorkspaceRequest({}, delegateSnapshot)
    const token = wsCache.get('user.token')
    const heads: any = {
      'Content-Type': 'application/json',
    }
    if (token) {
      heads['X-SHUZHI-TOKEN'] = `Bearer ${token}`
    }
    const tenantId = delegateSnapshot.tenantId || workspaceSnapshot.tenantId
    if (tenantId) {
      heads['X-SHUZHI-TENANT-ID'] = String(tenantId)
    }
    if (delegateSnapshot.active) {
      heads[PLATFORM_WORKSPACE_DELEGATE_HEADER] = '1'
    }
    if (assistantStore.getToken) {
      const prefix = assistantStore.getType === 4 ? 'Embedded ' : 'Assistant '
      heads['X-SHUZHI-ASSISTANT-TOKEN'] = `${prefix}${assistantStore.getToken}`
      if (heads['X-SHUZHI-TOKEN']) delete heads['X-SHUZHI-TOKEN']
      if (
        assistantStore.getType &&
        !!(assistantStore.getType % 2) &&
        assistantStore.getCertificate
      ) {
        await assistantStore.refreshCertificate(url)
        heads['X-SHUZHI-ASSISTANT-CERTIFICATE'] = btoa(
          encodeURIComponent(assistantStore.getCertificate)
        )
      }
      if (assistantStore.getHostOrigin) {
        heads['X-SHUZHI-HOST-ORIGIN'] = assistantStore.getHostOrigin
      }
      if (!assistantStore.getType || assistantStore.getType === 2) {
        heads['X-SHUZHI-ASSISTANT-ONLINE'] = assistantStore.getOnline
      }
    }

    const real_url = import.meta.env.VITE_API_BASE_URL
    const response = await fetch(real_url + url, {
      method: 'POST',
      headers: heads,
      body: JSON.stringify(data),
      signal: controller?.signal,
    })
    const responseTenantId = response.headers.get(TENANT_CONTEXT_HEADER) || ''
    assertPlatformWorkspaceDelegateSnapshot(delegateSnapshot, responseTenantId)
    workspaceContext.assertConsumable(workspaceSnapshot, responseTenantId)
    return response
  }

  // PUT request
  public put<T = any>(url: string, data?: any, config?: FullRequestConfig): Promise<T> {
    return this.request({ ...config, method: 'PUT', url, data })
  }

  // DELETE request
  public delete<T = any>(url: string, config?: FullRequestConfig): Promise<T> {
    return this.request({ ...config, method: 'DELETE', url })
  }

  // PATCH request
  public patch<T = any>(url: string, data?: any, config?: FullRequestConfig): Promise<T> {
    return this.request({ ...config, method: 'PATCH', url, data })
  }

  // File upload
  public upload<T = any>(
    url: string,
    file: File,
    fieldName = 'file',
    config?: FullRequestConfig
  ): Promise<T> {
    const formData = new FormData()
    formData.append(fieldName, file)

    return this.post(url, formData, {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
      ...config,
    })
  }

  // Download file
  public download(url: string, config?: FullRequestConfig): Promise<Blob> {
    return this.request<Blob>({
      ...config,
      method: 'GET',
      url,
      responseType: 'blob',
    })
  }

  public loadRemoteScript(url: string, id?: string, cb?: any): Promise<HTMLElement> {
    if (!url) {
      return Promise.reject(new Error('URL is required to load remote script'))
    }
    if (id && document.getElementById(id)) {
      return Promise.resolve(document.getElementById(id) as HTMLElement)
    }
    if (url.startsWith('/')) {
      const real_url = import.meta.env.VITE_API_BASE_URL.replace('/api/v1', '')
      url = real_url + url
    }
    return new Promise<HTMLElement>((resolve, reject) => {
      // 改用传统的script标签加载方式
      const script = document.createElement('script')
      script.src = url
      script.id = id || `remote-script-${Date.now()}`

      script.onload = () => {
        if (cb) cb()
        resolve(script)
      }

      script.onerror = (error) => {
        console.error(`Failed to load script from ${url}:`, error)
        reject(new Error(`Failed to load script from ${url}`))
      }

      document.head.appendChild(script)
    })
  }
  /* public loadRemoteScript(url: string, id?: string, cb?: any): Promise<HTMLElement> {
    if (!url) {
      return Promise.reject(new Error('URL is required to load remote script'))
    }
    if (id && document.getElementById(id)) {
      return Promise.resolve(document.getElementById(id) as HTMLElement)
    }
    return new Promise<HTMLElement>((resolve, reject) => {
      this.get(url, {
        responseType: 'text',
        headers: {
          'Content-Type': 'application/javascript',
        },
      })
        .then((response: any) => {
          const script = document.createElement('script')
          script.textContent = response
          script.id = id || `remote-script-${Date.now()}`
          // Append script to head
          document.head.appendChild(script)
          if (cb) {
            cb()
          }
          resolve(script)
        })
        .catch((error: any) => {
          console.error(`Failed to load script from ${url}:`, error)
          reject(new Error(`Failed to load script from ${url}: ${error.message}`))
        })
    })
  } */
}

// Create singleton instance
export const request = new HttpService({
  baseURL: import.meta.env.VITE_API_BASE_URL,
})
