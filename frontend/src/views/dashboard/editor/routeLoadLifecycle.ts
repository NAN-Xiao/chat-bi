export const createRouteLoadLifecycle = () => {
  let version = 0
  let disposed = false

  return {
    begin() {
      version += 1
      return version
    },
    isCurrent(loadVersion: number) {
      return !disposed && loadVersion === version
    },
    dispose() {
      disposed = true
      version += 1
    },
  }
}
