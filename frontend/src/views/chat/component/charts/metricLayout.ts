import type { ChartLayoutContext } from '@/views/chat/component/chartLayout.ts'

export interface MetricLayout {
  showInnerLabel: boolean
  showAccent: boolean
  wrapperPadding: string
  cardPadding: string
  valueFontSize: number
  valueLineHeight: number
  comparisonColumns: number
  comparisonGap: string
  requiredHeight: number
}

export function resolveMetricLayout(
  context: ChartLayoutContext,
  compareCount: number
): MetricLayout {
  if (context.density === 'mini') {
    return {
      showInnerLabel: !(context.surface === 'dashboard' && context.hasOuterTitle),
      showAccent: false,
      wrapperPadding: '0 4px',
      cardPadding: '0 6px',
      valueFontSize: 26,
      valueLineHeight: 30,
      comparisonColumns: compareCount > 1 && context.width >= 180 ? 2 : 1,
      comparisonGap: '2px 10px',
      requiredHeight: context.surface === 'dashboard' && context.hasOuterTitle ? 68 : 79,
    }
  }
  if (context.density === 'basic') {
    return {
      showInnerLabel: true,
      showAccent: true,
      wrapperPadding: '2px 6px 4px',
      cardPadding: '6px 10px 8px',
      valueFontSize: 28,
      valueLineHeight: 34,
      comparisonColumns: compareCount > 1 ? 2 : 1,
      comparisonGap: '4px 12px',
      requiredHeight: 132,
    }
  }
  return {
    showInnerLabel: true,
    showAccent: true,
    wrapperPadding: '6px 10px 10px',
    cardPadding: '12px 18px 14px',
    valueFontSize: 36,
    valueLineHeight: 44,
    comparisonColumns: compareCount > 1 ? 2 : 1,
    comparisonGap: '6px 14px',
    requiredHeight: 174,
  }
}
