import { BaseChart } from '@/views/chat/component/BaseChart.ts'
import { axisLabel, type ChartAxis } from '@/views/chat/component/BaseChart.ts'
import {
  formatNumber,
  isPercentAxis,
  toNullableNumber,
} from '@/views/chat/component/charts/utils.ts'
import { chartPalette } from '@/views/chat/component/charts/theme.ts'

export class Metric extends BaseChart {
  container: HTMLElement | null = null

  constructor(id: string) {
    super(id, 'metric')
    this.container = document.getElementById(id)
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

    if (rawName && !isMachineField(rawName)) {
      return normalize(rawName)
    }
    if (rawValue && !isMachineField(rawValue)) {
      return normalize(rawValue)
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

    const frameWidth = this.container.clientWidth || 0
    const frameHeight = this.container.clientHeight || 0
    const compactFrame = frameWidth > 0 && frameWidth < 260
    const shallowFrame = frameHeight > 0 && frameHeight < 220
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

    this.container.innerHTML = ''
    const wrapper = document.createElement('div')
    Object.assign(wrapper.style, {
      width: '100%',
      minHeight: '100%',
      display: 'grid',
      gridTemplateColumns: compactFrame
        ? 'minmax(0, 1fr)'
        : 'repeat(auto-fit, minmax(min(180px, 100%), 1fr))',
      gap: shallowFrame ? '6px' : '12px',
      alignItems: 'start',
      alignContent: 'start',
      padding: compactFrame || shallowFrame ? '2px 4px 6px' : '6px 10px 10px',
      boxSizing: 'border-box',
      overflow: 'hidden',
    })

    axes.forEach((axis) => {
      const card = document.createElement('div')
      Object.assign(card.style, {
        minWidth: '0',
        width: '100%',
        border: '0',
        borderRadius: '8px',
        background: '#fff',
        padding: compactFrame || shallowFrame ? '8px 10px 10px' : '12px 18px 14px',
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'flex-start',
        justifyContent: 'flex-start',
        boxShadow: 'none',
      })

      const label = document.createElement('div')
      const axisLabel = this.displayAxisName(axis)
      label.textContent = axisLabel
      Object.assign(label.style, {
        color: '#6b7a90',
        fontSize: compactFrame || shallowFrame ? '12px' : '13px',
        lineHeight: compactFrame || shallowFrame ? '18px' : '20px',
        maxWidth: '100%',
        overflow: 'hidden',
        textOverflow: 'ellipsis',
        whiteSpace: 'nowrap',
      })

      if (axisLabel && dateAxis) {
        const date = document.createElement('div')
        date.textContent = String(firstRow[dateAxis.value])
        Object.assign(date.style, {
          color: '#6b7a90',
          fontSize: '11px',
          lineHeight: '16px',
          marginTop: compactFrame || shallowFrame ? '2px' : '6px',
          maxWidth: '100%',
          overflow: 'hidden',
          textOverflow: 'ellipsis',
          whiteSpace: 'nowrap',
        })
        card.appendChild(label)
        card.appendChild(date)
      } else {
        if (axisLabel) {
          card.appendChild(label)
        }
      }

      const value = document.createElement('div')
      const rawValue = firstRow[axis.value]
      value.textContent = this.formatValue(rawValue, axis)
      Object.assign(value.style, {
        color: '#15233b',
        fontSize: compactFrame ? '24px' : shallowFrame ? '28px' : '36px',
        fontWeight: '700',
        lineHeight: compactFrame ? '30px' : shallowFrame ? '34px' : '44px',
        marginTop: compactFrame || shallowFrame ? '4px' : '6px',
        maxWidth: '100%',
        overflow: 'hidden',
        textOverflow: 'ellipsis',
        whiteSpace: 'nowrap',
      })

      const compareRow = document.createElement('div')
      Object.assign(compareRow.style, {
        display: 'flex',
        flexWrap: 'wrap',
        gap: '6px 14px',
        minHeight: '18px',
        marginTop: compactFrame || shallowFrame ? '4px' : '8px',
        color: '#667891',
        fontSize: '12px',
        lineHeight: '18px',
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
          maxWidth: '140px',
          overflow: 'hidden',
          textOverflow: 'ellipsis',
          whiteSpace: 'nowrap',
        })
        compareRow.appendChild(compareItem)
      })

      const accent = document.createElement('div')
      Object.assign(accent.style, {
        width: compactFrame ? '28px' : '36px',
        height: '4px',
        borderRadius: '999px',
        background: chartPalette[axes.indexOf(axis) % chartPalette.length],
        marginTop: compactFrame || shallowFrame ? '6px' : '10px',
      })

      card.appendChild(value)
      if (compareAxes.length > 0) {
        card.appendChild(compareRow)
      }
      card.appendChild(accent)
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
