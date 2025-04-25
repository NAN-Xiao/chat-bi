import { request } from '@/utils/request'

export const AuthApi = {
  login: (credentials: { username: string; password: string }) => request.post<{
    data: any; token: string 
}>('/login/access-token', credentials, {
    headers: {
      'Content-Type': 'application/x-www-form-urlencoded'
    },
    requestOptions: {
      rawResponse: true,
    }
  }),
  logout: () => request.post('/auth/logout')
}