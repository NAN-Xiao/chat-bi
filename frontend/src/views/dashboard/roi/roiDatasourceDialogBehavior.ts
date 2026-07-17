const ROI_CONFIG_CONFLICT_MESSAGES = new Set([
  '已有 ROI 图表时不能更换数据源',
  '数据已被其他人修改，请刷新后重试',
  'ROI 配置已被其他人创建或修改，请刷新后重试',
])

const ROI_CONFIG_SAVE_FALLBACK = '保存 ROI 数据源失败，请稍后重试'

export function createRoiDatasourceDialogCloseGuard() {
  let generation = 0
  let saveSequence = 0
  let phase: 'closed' | 'open' | 'cancelled' | 'saved' = 'closed'

  const isCurrent = (token: { generation: number; saveSequence: number } | null) =>
    token !== null && token.generation === generation && phase === 'open'

  return {
    beginOpen() {
      generation += 1
      phase = 'open'
    },
    beginSave() {
      if (phase !== 'open') return null
      saveSequence += 1
      return { generation, saveSequence }
    },
    isCurrent,
    markSaved(token: { generation: number; saveSequence: number } | null) {
      if (!isCurrent(token)) return false
      phase = 'saved'
      return true
    },
    beginCancel() {
      if (phase !== 'open') return false
      phase = 'cancelled'
      generation += 1
      return true
    },
  }
}

export function getRoiDatasourceSaveErrorMessage(error: unknown): string {
  const response = (error as { response?: { status?: number; data?: unknown } })?.response
  if (Number(response?.status) !== 409) return ROI_CONFIG_SAVE_FALLBACK
  const data = response?.data
  const detail =
    data && typeof data === 'object' && 'detail' in data
      ? (data as { detail?: unknown }).detail
      : undefined
  return typeof detail === 'string' && ROI_CONFIG_CONFLICT_MESSAGES.has(detail)
    ? detail
    : ROI_CONFIG_SAVE_FALLBACK
}
