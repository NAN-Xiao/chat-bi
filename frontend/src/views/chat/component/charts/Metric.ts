import { BaseChart } from '@/views/chat/component/BaseChart.ts'
import { formatNumber } from '@/views/chat/component/charts/utils.ts'
import { chartPalette } from '@/views/chat/component/charts/theme.ts'

export class Metric extends BaseChart {
  container: HTMLElement | null = null

  constructor(id: string) {
    super(id, 'metric')
    this.container = document.getElementById(id)
  }

  render() {
    if (!this.container) {
      return
    }

    const firstRow = this.data[0] || {}
    const valueAxes = this.axis.filter((axis) => axis.type === 'y')
    const fallbackAxes = this.axis.filter((axis) => !axis.hidden)
    const axes = (valueAxes.length > 0 ? valueAxes : fallbackAxes).slice(0, 6)

    this.container.innerHTML = ''
    const wrapper = document.createElement('div')
    Object.assign(wrapper.style, {
      width: '100%',
      height: '100%',
      display: 'grid',
      gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))',
      gap: '12px',
      alignItems: 'stretch',
      padding: '8px',
      boxSizing: 'border-box',
    })

    axes.forEach((axis) => {
      const card = document.createElement('div')
      Object.assign(card.style, {
        minWidth: '0',
        border: '0',
        borderRadius: '8px',
        background: '#fff',
        padding: '16px',
        display: 'flex',
        flexDirection: 'column',
        justifyContent: 'center',
        boxShadow: 'none',
      })

      const label = document.createElement('div')
      label.textContent = axis.name || axis.value
      Object.assign(label.style, {
        color: '#6b7a90',
        fontSize: '13px',
        lineHeight: '20px',
        overflow: 'hidden',
        textOverflow: 'ellipsis',
        whiteSpace: 'nowrap',
      })

      const value = document.createElement('div')
      const rawValue = firstRow[axis.value]
      value.textContent =
        rawValue === null || rawValue === undefined || rawValue === ''
          ? '-'
          : String(formatNumber(rawValue))
      Object.assign(value.style, {
        color: '#15233b',
        fontSize: '28px',
        fontWeight: '700',
        lineHeight: '36px',
        marginTop: '8px',
        overflow: 'hidden',
        textOverflow: 'ellipsis',
        whiteSpace: 'nowrap',
      })

      const accent = document.createElement('div')
      Object.assign(accent.style, {
        width: '28px',
        height: '3px',
        borderRadius: '999px',
        background: chartPalette[axes.indexOf(axis) % chartPalette.length],
        marginTop: '12px',
      })

      card.appendChild(label)
      card.appendChild(value)
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
