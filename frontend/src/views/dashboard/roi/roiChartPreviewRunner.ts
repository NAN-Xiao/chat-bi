import type { RoiChartPreviewResponse } from './types'

export const ROI_CHART_PREVIEW_ERROR_MESSAGE = '预览 ROI 图表失败，请稍后重试'

interface RoiPreviewToken {
  session: number
  request: number
  signature: string
}

interface RoiPreviewGuard {
  beginPreview(signature: string): RoiPreviewToken
  isActivePreview(token: RoiPreviewToken): boolean
  markPreviewSucceeded(token: RoiPreviewToken, currentSignature: string): boolean
  invalidatePreview(): void
}

interface RoiChartPreviewRunnerOptions<Payload> {
  guard: RoiPreviewGuard
  request: (payload: Payload) => Promise<RoiChartPreviewResponse>
  getCurrentSignature: () => string
  onSuccess: (result: RoiChartPreviewResponse) => void
  onError: (message: string) => void
  onLoading: (loading: boolean) => void
}

export function createRoiChartPreviewRunner<Payload>(
  options: RoiChartPreviewRunnerOptions<Payload>
) {
  let generation = 0
  let activeGeneration = 0
  let loading = false

  const setLoading = (value: boolean) => {
    if (loading === value) return
    loading = value
    options.onLoading(value)
  }

  const invalidate = () => {
    activeGeneration = ++generation
    options.guard.invalidatePreview()
    setLoading(false)
  }

  return {
    async run(payload: Payload, signature: string) {
      const currentGeneration = ++generation
      activeGeneration = currentGeneration
      const token = options.guard.beginPreview(signature)
      setLoading(true)
      try {
        const result = await options.request(payload)
        if (currentGeneration !== activeGeneration || !options.guard.isActivePreview(token)) {
          return
        }
        if (result.status !== 'success') {
          options.guard.invalidatePreview()
          options.onError(ROI_CHART_PREVIEW_ERROR_MESSAGE)
          return
        }
        if (!options.guard.markPreviewSucceeded(token, options.getCurrentSignature())) return
        options.onSuccess({
          status: 'success',
          fields: [...(result.fields || [])],
          data: [...(result.data || [])],
          message: '',
        })
      } catch {
        if (currentGeneration === activeGeneration && options.guard.isActivePreview(token)) {
          options.guard.invalidatePreview()
          options.onError(ROI_CHART_PREVIEW_ERROR_MESSAGE)
        }
      } finally {
        if (currentGeneration === activeGeneration) setLoading(false)
      }
    },
    invalidate,
  }
}
