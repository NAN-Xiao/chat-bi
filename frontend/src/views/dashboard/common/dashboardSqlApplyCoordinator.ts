export type DashboardSqlApplyOptions<T> = {
  viewInfo?: T | null
  isApplying: () => boolean
  setApplying: (value: boolean) => void
  validate: () => boolean
  write: () => boolean
  execute?: (viewInfo: T) => Promise<boolean>
  onApplied: (viewInfo: T) => void
  close: () => void
  notify: () => void
}

export async function runDashboardSqlApply<T>(options: DashboardSqlApplyOptions<T>) {
  const viewInfo = options.viewInfo
  if (!viewInfo || options.isApplying() || !options.validate()) return false
  if (!options.write()) return false

  options.setApplying(true)
  try {
    if (options.execute) {
      const applied = await options.execute(viewInfo)
      if (!applied) return false
    }
    options.onApplied(viewInfo)
    options.close()
    options.notify()
    return true
  } finally {
    options.setApplying(false)
  }
}
