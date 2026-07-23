type DashboardLandingRedirectRequest<T> = {
  sourceFullPath: string
  getCurrentFullPath: () => string
  resolveLanding: () => Promise<T>
  commit: (target: T) => void | Promise<void>
}

export const createDashboardLandingRedirectCoordinator = () => {
  let generation = 0
  let activeToken: number | null = null

  return {
    async redirect<T>({
      sourceFullPath,
      getCurrentFullPath,
      resolveLanding,
      commit,
    }: DashboardLandingRedirectRequest<T>) {
      const token = ++generation
      activeToken = token
      try {
        const target = await resolveLanding()
        if (activeToken !== token || getCurrentFullPath() !== sourceFullPath) return
        await commit(target)
      } catch (error) {
        if (activeToken === token && getCurrentFullPath() === sourceFullPath) throw error
      } finally {
        if (activeToken === token) activeToken = null
      }
    },
    invalidate() {
      generation += 1
      activeToken = null
    },
    isResolving() {
      return activeToken !== null
    },
  }
}
