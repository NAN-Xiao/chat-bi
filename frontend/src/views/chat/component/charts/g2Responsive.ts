import type { ChartLayoutContext } from '@/views/chat/component/chartLayout.ts'

export type G2ChartFamily = 'cartesian' | 'structure'

export function resolveG2ResponsiveStyle(
  context: ChartLayoutContext | undefined,
  family: G2ChartFamily
) {
  const density = context?.density || 'regular'
  if (density === 'mini') {
    return {
      padding: family === 'cartesian' ? [4, 6, 18, 28] : [4, 6, 16, 6],
      axisLabelFontSize: 9,
      structureLabelFontSize: 9,
      legendPosition: 'bottom' as const,
      legendItemFontSize: 10,
      showPointLabels: false,
      outerRadius: 0.7,
    }
  }
  if (density === 'basic') {
    return {
      padding: family === 'cartesian' ? [8, 10, 22, 34] : [6, 8, 20, 8],
      axisLabelFontSize: 10,
      structureLabelFontSize: 10,
      legendPosition: 'bottom' as const,
      legendItemFontSize: 11,
      showPointLabels: false,
      outerRadius: 0.76,
    }
  }
  return {
    padding: 'auto' as const,
    axisLabelFontSize: 11,
    structureLabelFontSize: 11,
    legendPosition: 'bottom' as const,
    legendItemFontSize: 12,
    showPointLabels: true,
    outerRadius: 0.8,
  }
}
