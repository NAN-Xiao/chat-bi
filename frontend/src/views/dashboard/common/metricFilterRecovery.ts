export type MetricFilterRecoveryField = {
  value: string
  table?: string
  kind?: string
}

type MetricFilterRecoveryCandidateOptions = {
  metricField: string
  metricMeasureField: string
  metricFieldOption?: MetricFilterRecoveryField
  selectableFilterOptions: MetricFilterRecoveryField[]
  schemaFieldOptions: MetricFilterRecoveryField[]
}

function uniqueFieldValues(values: string[]) {
  return Array.from(new Set(values.filter(Boolean)))
}

export function metricFilterRecoveryCandidates({
  metricField,
  metricMeasureField,
  metricFieldOption,
  selectableFilterOptions,
  schemaFieldOptions,
}: MetricFilterRecoveryCandidateOptions) {
  if (metricFieldOption?.kind === 'tracking-event') {
    return uniqueFieldValues(selectableFilterOptions.map((option) => option.value))
  }

  return uniqueFieldValues([
    metricField,
    metricMeasureField,
    ...schemaFieldOptions
      .filter((option) => option.table === metricFieldOption?.table)
      .map((option) => option.value),
  ])
}
