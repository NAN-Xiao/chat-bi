import { request, type FullRequestConfig } from '@/utils/request'
export const AuthApi = {
  login: (credentials: { username: string; password: string }) => {
    const entryCredentials = {
      username: credentials.username,
      password: credentials.password,
    }
    return request.post<{
      data: any
      token: string
    }>('/login/access-token', entryCredentials, {
      headers: {
        'Content-Type': 'application/x-www-form-urlencoded',
      },
      requestOptions: { workspaceMode: 'none' },
    })
  },
  feishuStatus: (params?: { redirect?: string }, config?: FullRequestConfig) =>
    request.get('/login/feishu/status', {
      ...config,
      params,
      requestOptions: { workspaceMode: 'none', ...config?.requestOptions },
    }),
  feishuCallback: (data: { code: string; state: string }) =>
    request.post('/login/feishu/callback', data, {
      requestOptions: { workspaceMode: 'none' },
    }),
  submitTrialApplication: (data: {
    account: string
    password: string
    name: string
    email: string
    company?: string
    reason?: string
  }) =>
    request.post('/login/trial-application', data, {
      requestOptions: { workspaceMode: 'none' },
    }),
  logout: (data: any) =>
    request.post('/login/logout', data, {
      requestOptions: { workspaceMode: 'none' },
    }),
  info: (config?: FullRequestConfig) =>
    request.get('/user/info', {
      ...config,
      requestOptions: {
        workspaceMode: 'bootstrap',
        ...config?.requestOptions,
      },
    }),
}
