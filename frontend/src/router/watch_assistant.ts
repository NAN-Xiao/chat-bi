import { ElMessage } from 'element-plus-secondary'

import { request } from '@/utils/request'

export const watchRouter = (router: any) => {
  router.beforeEach(async (to: any, from: any, next: any) => {
    console.log(to, from)
    await loadXpackStatic()
    next()
  })
}
const loadXpackStatic = () => {
  if (document.getElementById('sqlbot_xpack_static')) {
    return Promise.resolve()
  }
  const url = '/xpack_static/license-generator.umd.js'
  return new Promise((resolve, reject) => {
    request
      .loadRemoteScript(url, 'sqlbot_xpack_static', () => {
        // eslint-disable-next-line @typescript-eslint/ban-ts-comment
        // @ts-ignore
        LicenseGenerator?.init(import.meta.env.VITE_API_BASE_URL).then(() => {
          resolve(true)
        })
      })
      .catch((error) => {
        console.error('Failed to load xpack_static script:', error)
        ElMessage.error('Failed to load license generator script')
        reject(error)
      })
  })
}
