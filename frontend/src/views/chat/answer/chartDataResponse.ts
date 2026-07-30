export function applyChartDataResponseToRecord(record: any, response: any) {
  record.data = response

  if (response?.status === 'failed') {
    const message = typeof response.message === 'string' ? response.message.trim() : ''
    const reason = typeof response.reason === 'string' ? response.reason.trim() : ''
    record.error =
      message ||
      reason ||
      (response.error_type === 'permission_denied' ? '没有查看权限' : '数据查询失败')
    return
  }

  record.error = undefined

  if (response?.status === 'business_notice') {
    record.chart = ''
    record.analysis_notice = response.notice
    record.analysis = response.message || response.reason || record.analysis
    return
  }

  record.analysis_notice = undefined
}
