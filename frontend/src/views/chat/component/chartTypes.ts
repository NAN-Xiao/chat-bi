export function isRadialPartitionChartType(type: string): type is 'pie' | 'donut' {
  return type === 'pie' || type === 'donut'
}
