import type { ChartLayoutContext } from '@/views/chat/component/chartLayout.ts'

export type G2ChartFamily = 'cartesian' | 'structure'

export interface G2ResponsiveStyle {
  padding: number[] | 'auto'
  axisLabelFontSize: number
  structureLabelFontSize: number
  legendPosition: 'bottom'
  legendItemFontSize: number
  outerRadius: number
  maxCategoryAxisLabels: number
}

function resolveMaxCategoryAxisLabels(
  context: ChartLayoutContext | undefined,
  minLabelGap: number,
  cap: number
): number {
  const width = Math.max(0, context?.width || 0)
  if (!width) return cap
  return Math.max(2, Math.min(cap, Math.floor(width / minLabelGap)))
}

function keepSampledAxisLabel(index: number, total: number, maxLabels: number): boolean {
  if (total <= maxLabels) return true
  if (index === 0 || index === total - 1) return true
  if (maxLabels <= 2) return false

  const innerSlots = maxLabels - 2
  const innerCount = total - 2
  const step = Math.max(1, Math.ceil(innerCount / innerSlots))
  return (index - 1) % step === 0
}

export function resolveG2ResponsiveStyle(
  context: ChartLayoutContext | undefined,
  family: G2ChartFamily
): G2ResponsiveStyle {
  const density = context?.density || 'regular'
  if (density === 'mini') {
    return {
      padding: family === 'cartesian' ? [4, 6, 18, 28] : [4, 6, 16, 6],
      axisLabelFontSize: 9,
      structureLabelFontSize: 9,
      legendPosition: 'bottom' as const,
      legendItemFontSize: 10,
      outerRadius: 0.7,
      maxCategoryAxisLabels: resolveMaxCategoryAxisLabels(context, 48, 6),
    }
  }
  if (density === 'basic') {
    return {
      padding: family === 'cartesian' ? [8, 10, 22, 34] : [6, 8, 20, 8],
      axisLabelFontSize: 10,
      structureLabelFontSize: 10,
      legendPosition: 'bottom' as const,
      legendItemFontSize: 11,
      outerRadius: 0.76,
      maxCategoryAxisLabels: resolveMaxCategoryAxisLabels(context, 54, 10),
    }
  }
  return {
    padding: 'auto' as const,
    axisLabelFontSize: 11,
    structureLabelFontSize: 11,
    legendPosition: 'bottom' as const,
    legendItemFontSize: 12,
    outerRadius: 0.8,
    maxCategoryAxisLabels: resolveMaxCategoryAxisLabels(context, 60, 16),
  }
}

export function resolveCategoryAxisResponsiveOptions(responsive: G2ResponsiveStyle) {
  return {
    labelFontSize: responsive.axisLabelFontSize,
    labelAutoHide: {
      type: 'hide',
      keepHeader: true,
      keepTail: true,
    },
    labelAutoRotate: false,
    labelAutoWrap: false,
    labelAutoEllipsis: false,
    labelFilter: (_datum: unknown, index: number, array?: unknown[]) => {
      if (!Array.isArray(array)) return true
      return keepSampledAxisLabel(index, array.length, responsive.maxCategoryAxisLabels)
    },
  }
}
