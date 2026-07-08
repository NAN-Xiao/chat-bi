export function applyChartDataResponseToRecord(record: any, response: any) {
  record.data = response

  if (response?.status === 'business_notice') {
    record.chart = ''
    record.analysis_notice = response.notice
    record.analysis = response.message || response.reason || record.analysis
    return
  }

  record.analysis_notice = undefined
}
