export type ChartDensity = 'mini' | 'basic' | 'regular'
export type ChartSurface = 'dashboard' | 'chat' | 'fullscreen' | 'preview'

export interface ChartLayoutContext {
  width: number
  height: number
  density: ChartDensity
  surface: ChartSurface
  hasOuterTitle: boolean
}

const MINI_MAX_WIDTH = 260
const MINI_MAX_HEIGHT = 120
const BASIC_MAX_WIDTH = 420
const BASIC_MAX_HEIGHT = 220
const DENSITY_HYSTERESIS = 8

function rawDensity(width: number, height: number): ChartDensity {
  if (width < MINI_MAX_WIDTH || height < MINI_MAX_HEIGHT) return 'mini'
  if (width < BASIC_MAX_WIDTH || height < BASIC_MAX_HEIGHT) return 'basic'
  return 'regular'
}

export function resolveChartDensity(
  width: number,
  height: number,
  previous?: ChartDensity
): ChartDensity {
  const next = rawDensity(width, height)
  if (
    previous === 'mini' &&
    (width < MINI_MAX_WIDTH + DENSITY_HYSTERESIS ||
      height < MINI_MAX_HEIGHT + DENSITY_HYSTERESIS)
  ) {
    return 'mini'
  }
  if (
    previous === 'basic' &&
    next === 'mini' &&
    width >= MINI_MAX_WIDTH - DENSITY_HYSTERESIS &&
    height >= MINI_MAX_HEIGHT - DENSITY_HYSTERESIS
  ) {
    return 'basic'
  }
  if (
    previous === 'basic' &&
    next === 'regular' &&
    (width < BASIC_MAX_WIDTH + DENSITY_HYSTERESIS ||
      height < BASIC_MAX_HEIGHT + DENSITY_HYSTERESIS)
  ) {
    return 'basic'
  }
  if (
    previous === 'regular' &&
    next === 'basic' &&
    width >= BASIC_MAX_WIDTH - DENSITY_HYSTERESIS &&
    height >= BASIC_MAX_HEIGHT - DENSITY_HYSTERESIS
  ) {
    return 'regular'
  }
  return next
}

export function buildChartLayoutContext(params: {
  width: number
  height: number
  surface?: ChartSurface
  hasOuterTitle?: boolean
  previousDensity?: ChartDensity
}): ChartLayoutContext {
  const width = Math.max(0, Math.round(params.width))
  const height = Math.max(0, Math.round(params.height))
  return {
    width,
    height,
    density: resolveChartDensity(width, height, params.previousDensity),
    surface: params.surface || 'preview',
    hasOuterTitle: params.hasOuterTitle === true,
  }
}
