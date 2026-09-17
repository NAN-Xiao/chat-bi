/** Restore saved results from the former date-dimension stop response. */
export function needsQueryResultTable(record: any): boolean {
  return !!record && !record.error && record.analysis_notice?.reason === 'chart_dimension_unavailable'
}

export function restoreQueryResultTable(record: any): void {
  if (!needsQueryResultTable(record)) return
  let data = record.data
  try {
    if (typeof data === 'string') data = JSON.parse(data)
    if (record.chart && JSON.parse(record.chart)?.type !== 'table') return
  } catch {
    return
  }
  if (!data || data.status === 'failed' || data.status === 'business_notice') return
  if (!Array.isArray(data.fields) || !data.fields.length || !Array.isArray(data.data)) return
  if (!record.chart) {
    record.chart = JSON.stringify({
      type: 'table', title: '查询结果', columns: data.fields.map((field: string) => ({ value: field })),
    })
  }
  record.analysis_notice = undefined
  record.analysis = ''
}
