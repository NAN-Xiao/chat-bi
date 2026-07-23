export function getRoiChartSaveErrorMessage(error: unknown): string {
  const status = Number((error as any)?.response?.status)
  return status === 409 ? '数据已被其他人修改，请刷新后重试' : '保存 ROI 图表失败，请稍后重试'
}
