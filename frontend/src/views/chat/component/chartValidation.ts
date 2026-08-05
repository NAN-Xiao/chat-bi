export class ChartValidationError extends Error {
  constructor(public readonly code: string) {
    super(code)
    this.name = 'ChartValidationError'
  }
}

export function isChartValidationError(error: unknown): error is ChartValidationError {
  return error instanceof ChartValidationError
}
