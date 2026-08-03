import { BaseChart } from '@/views/chat/component/BaseChart.ts'
import { axisLabel, type ChartAxis, type ChartMountTarget } from '@/views/chat/component/BaseChart.ts'
import { buildChartLayoutContext } from '@/views/chat/component/chartLayout.ts'
import {
  formatNumber,
  isPercentAxis,
  toNullableNumber,
} from '@/views/chat/component/charts/utils.ts'
import { chartPalette } from '@/views/chat/component/charts/theme.ts'
import { resolveMetricLayout } from '@/views/chat/component/charts/metricLayout.ts'

export class Metric extends BaseChart {
  container: HTMLElement | null = null

  constructor(mountTarget: ChartMountTarget) {
    super(mountTarget, 'metric')
    this.container =
      typeof mountTarget === 'string' ? document.getElementById(mountTarget) : mountTarget
  }

  private isBlank(value: any) {
    return value === null || value === undefined || value === ''
  }

  private formatValue(value: any, axis: ChartAxis) {
    if (this.isBlank(value)) {
      return '-'
    }
    if (typeof value === 'string' && value.trim().endsWith('%')) {
      return value.trim()
    }

    const numericValue = toNullableNumber(value)
    if (numericValue === null) {
      return String(value)
    }

    const isPercent = isPercentAxis(axis, this.data)
    const displayValue = isPercent && Math.abs(numericValue) <= 1 ? numericValue * 100 : numericValue
    return `${formatNumber(displayValue)}${isPercent ? '%' : ''}`
  }

  private isDateLike(value: any) {
    if (this.isBlank(value)) {
      return false
    }
    const text = String(value).trim()
    return (
      /^\d{4}[-/]\d{1,2}[-/]\d{1,2}/.test(text) ||
      /^\d{4}[-/]\d{1,2}$/.test(text) ||
      /^\d{1,2}[-/]\d{1,2}$/.test(text)
    )
  }

  private displayAxisName(axis: ChartAxis) {
    const rawName = axisLabel(axis)
    const rawValue = String(axis.value || '').trim()
    const normalize = (text: string) =>
      text
        .replace(/[_-]+/g, ' ')
        .replace(/\s+/g, ' ')
        .trim()
    const isMachineField = (text: string) => /^[a-z][a-z0-9_]*$/.test(text)
    const machineFieldLabel = (text: string) => {
      const normalized = text.trim().toLowerCase()
      if (normalized.endsWith('_pct')) {
        return `${normalize(normalized.slice(0, -4))} %`
      }
      return normalize(normalized)
    }

    if (rawName && !isMachineField(rawName)) {
      return normalize(rawName)
    }
    if (rawValue && !isMachineField(rawValue)) {
      return normalize(rawValue)
    }
    if (rawName || rawValue) {
      return machineFieldLabel(rawName || rawValue)
    }
    return ''
  }

  private isCompareAxis(axis: ChartAxis) {
    const text = `${axisLabel(axis)} ${axis.value ?? ''}`.toLowerCase()
    return [
      'mom',
      'yoy',
      'wow',
      'dod',
      'qoq',
      'compare',
      'change',
      'growth',
      'delta',
      '环比',
      '同比',
      '周比',
      '月比',
      '年比',
      '变化',
      '增长',
      '增幅',
    ].some((keyword) => text.includes(keyword))
  }

  private compareTone(value: any) {
    const numericValue = toNullableNumber(value)
    if (numericValue === null) {
      return '#667891'
    }
    if (numericValue > 0) {
      return '#0c9b6d'
    }
    if (numericValue < 0) {
      return '#e05252'
    }
    return '#667891'
  }

  private formatCompareValue(value: any, axis: ChartAxis) {
    if (this.isBlank(value)) {
      return '-'
    }
    if (typeof value === 'string' && value.trim().endsWith('%')) {
      const text = value.trim()
      return text.startsWith('-') || text.startsWith('+') ? text : `+${text}`
    }

    const numericValue = toNullableNumber(value)
    if (numericValue === null) {
      return String(value)
    }

    const isPercent = isPercentAxis(axis, this.data)
    const displayValue = isPercent && Math.abs(numericValue) <= 1 ? numericValue * 100 : numericValue
    const prefix = displayValue > 0 ? '+' : ''
    return `${prefix}${formatNumber(displayValue)}${isPercent ? '%' : ''}`
  }

  render() {
    if (!this.container) {
      return
    }

    const firstRow = this.data[0] || {}
    const valueAxes = this.axis.filter((axis) => axis.type === 'y')
    const compareValueAxes = valueAxes.filter((axis) => this.isCompareAxis(axis))
    const primaryValueAxes = valueAxes.filter((axis) => !this.isCompareAxis(axis))
    const fallbackAxes = this.axis.filter((axis) => !axis.hidden)
    const axes = (
      primaryValueAxes.length > 0 ? primaryValueAxes : valueAxes.length > 0 ? valueAxes : fallbackAxes
    ).slice(0, 6)
    const axisValueSet = new Set(axes.map((axis) => axis.value))
    const infoAxes = this.axis.filter((axis) => !axis.hidden && !axisValueSet.has(axis.value))
    const dateAxis = infoAxes.find((axis) => this.isDateLike(firstRow[axis.value]))
    const compareAxes = [...compareValueAxes, ...infoAxes.filter((axis) => this.isCompareAxis(axis))]
      .filter((axis, index, list) => list.findIndex((item) => item.value === axis.value) === index)
      .slice(0, 2)
    const context =
      this.layoutContext ||
      buildChartLayoutContext({
        width: this.container.clientWidth,
        height: this.container.clientHeight,
        surface: 'preview',
      })
    const layout = resolveMetricLayout(this.layoutContext || context, compareAxes.length)
    const isMini = context.density === 'mini'

    this.container.innerHTML = ''
    const wrapper = document.createElement('div')
    wrapper.className = 'metric-wrapper'
    Object.assign(wrapper.style, {
      width: '100%',
      height: '100%',
      display: 'grid',
      gridTemplateColumns: isMini
        ? 'minmax(0, 1fr)'
        : 'repeat(auto-fit, minmax(min(180px, 100%), 1fr))',
      gap: isMini ? '4px' : '12px',
      alignItems: 'start',
      alignContent: 'start',
      padding: layout.wrapperPadding,
      boxSizing: 'border-box',
      overflow: 'hidden',
    })

    axes.forEach((axis) => {
      const card = document.createElement('div')
      card.className = 'metric-card'
      Object.assign(card.style, {
        minWidth: '0',
        width: '100%',
        border: '0',
        borderRadius: '8px',
        background: '#fff',
        padding: layout.cardPadding,
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'flex-start',
        justifyContent: 'flex-start',
        boxShadow: 'none',
        boxSizing: 'border-box',
        overflow: 'hidden',
      })

      const label = document.createElement('div')
      const metricLabel = this.displayAxisName(axis)
      label.textContent = metricLabel
      Object.assign(label.style, {
        color: '#6b7a90',
        fontSize: isMini ? '11px' : '13px',
        lineHeight: isMini ? '15px' : '20px',
        maxWidth: '100%',
        overflow: 'hidden',
        textOverflow: 'ellipsis',
        whiteSpace: 'nowrap',
      })

      const date = document.createElement('div')
      date.className = 'metric-date'
      if (dateAxis) {
        date.textContent = String(firstRow[dateAxis.value])
        Object.assign(date.style, {
          color: '#6b7a90',
          fontSize: '11px',
          lineHeight: isMini ? '15px' : '16px',
          marginTop: layout.showInnerLabel && metricLabel ? (isMini ? '1px' : '6px') : '0',
          maxWidth: '100%',
          overflow: 'hidden',
          textOverflow: 'ellipsis',
          whiteSpace: 'nowrap',
        })
      }

      if (layout.showInnerLabel && metricLabel) {
        card.appendChild(label)
      }
      if (dateAxis) {
        card.appendChild(date)
      }

      const value = document.createElement('div')
      value.className = 'metric-value'
      const rawValue = firstRow[axis.value]
      value.textContent = this.formatValue(rawValue, axis)
      Object.assign(value.style, {
        color: '#15233b',
        fontSize: `${layout.valueFontSize}px`,
        fontWeight: '700',
        lineHeight: `${layout.valueLineHeight}px`,
        marginTop: isMini ? '1px' : '6px',
        maxWidth: '100%',
        overflow: 'hidden',
        textOverflow: 'ellipsis',
        whiteSpace: 'nowrap',
      })

      const compareRow = document.createElement('div')
      compareRow.className = 'metric-comparisons'
      Object.assign(compareRow.style, {
        display: 'grid',
        gridTemplateColumns: `repeat(${layout.comparisonColumns}, minmax(0, 1fr))`,
        gap: layout.comparisonGap,
        minHeight: isMini ? '16px' : '18px',
        marginTop: isMini ? '1px' : '8px',
        color: '#667891',
        fontSize: isMini ? '11px' : '12px',
        lineHeight: isMini ? '16px' : '18px',
        width: '100%',
        minWidth: '0',
      })

      compareAxes.forEach((compareAxis) => {
        const compareItem = document.createElement('span')
        const compareValue = firstRow[compareAxis.value]
        const compareLabel = this.displayAxisName(compareAxis)
        if (!compareLabel) {
          return
        }
        compareItem.textContent = `${compareLabel} ${this.formatCompareValue(
          compareValue,
          compareAxis
        )}`
        compareItem.title = compareItem.textContent
        Object.assign(compareItem.style, {
          color: this.compareTone(compareValue),
          maxWidth: '100%',
          overflow: 'hidden',
          textOverflow: 'ellipsis',
          whiteSpace: 'nowrap',
          minWidth: '0',
        })
        compareRow.appendChild(compareItem)
      })

      const accent = document.createElement('div')
      Object.assign(accent.style, {
        width: isMini ? '28px' : '36px',
        height: '4px',
        borderRadius: '999px',
        background: chartPalette[axes.indexOf(axis) % chartPalette.length],
        marginTop: isMini ? '6px' : '10px',
      })

      card.appendChild(value)
      if (compareAxes.length > 0) {
        card.appendChild(compareRow)
      }
      if (layout.showAccent) {
        card.appendChild(accent)
      }
      wrapper.appendChild(card)
    })

    this.container.appendChild(wrapper)
  }

  destroy() {
    if (this.container) {
      this.container.innerHTML = ''
    }
  }
}
