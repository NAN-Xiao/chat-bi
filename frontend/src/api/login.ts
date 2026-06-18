import { request } from '@/utils/request'
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
    })
  },
  feishuStatus: (params?: { redirect?: string }) => request.get('/login/feishu/status', { params }),
  feishuCallback: (data: { code: string; state: string }) =>
    request.post('/login/feishu/callback', data),
  logout: (data: any) => request.post('/login/logout', data),
  info: () => request.get('/user/info'),
}
