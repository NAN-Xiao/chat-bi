import { formatChangePercent, formatMetricValue } from '@/views/chat/component/charts/utils.ts'

interface InsightMetric {
  label: string
  value: string
  tone?: 'neutral' | 'positive' | 'negative'
}

export function createInsightStrip(metrics: InsightMetric[]): HTMLElement | undefined {
  const visibleMetrics = metrics.filter((metric) => metric.value !== '-' && metric.value !== '')
  if (visibleMetrics.length === 0) {
    return undefined
  }

  const strip = document.createElement('div')
  Object.assign(strip.style, {
    display: 'flex',
    flexWrap: 'wrap',
    alignItems: 'center',
    gap: '8px 18px',
    padding: '0 4px 10px',
    color: '#66758f',
    fontSize: '12px',
    lineHeight: '18px',
  })

  visibleMetrics.forEach((metric, index) => {
    const item = document.createElement('div')
    Object.assign(item.style, {
      display: 'inline-flex',
      alignItems: 'baseline',
      gap: '6px',
      minWidth: '0',
    })

    const label = document.createElement('span')
    label.textContent = metric.label
    Object.assign(label.style, {
      color: '#8a97aa',
      whiteSpace: 'nowrap',
    })

    const value = document.createElement('span')
    value.textContent = metric.value
    Object.assign(value.style, {
      color:
        metric.tone === 'positive' ? '#28b879' : metric.tone === 'negative' ? '#f56c6c' : '#1b2a41',
      fontSize: index === 0 ? '18px' : '13px',
      fontWeight: index === 0 ? '700' : '600',
      lineHeight: index === 0 ? '24px' : '18px',
      whiteSpace: 'nowrap',
    })

    item.appendChild(label)
    item.appendChild(value)
    strip.appendChild(item)
  })

  return strip
}

export function getChangeTone(value: number | null | undefined): InsightMetric['tone'] {
  if (value === null || value === undefined || value === 0 || !Number.isFinite(value)) {
    return 'neutral'
  }
  return value > 0 ? 'positive' : 'negative'
}

export function createTrendInsight(params: {
  valueLabel: string
  latestValue: number | null
  changePercent: number | null
  maxLabel?: string
  maxValue: number | null
  isPercent?: boolean
}): HTMLElement | undefined {
  return createInsightStrip([
    {
      label: params.valueLabel,
      value: formatMetricValue(params.latestValue, { isPercent: params.isPercent }),
    },
    {
      label: '较上一项',
      value: formatChangePercent(params.changePercent),
      tone: getChangeTone(params.changePercent),
    },
    {
      label: params.maxLabel ? `最高 ${params.maxLabel}` : '最高值',
      value: formatMetricValue(params.maxValue, { isPercent: params.isPercent }),
    },
  ])
}

export function createCategoryInsight(params: {
  valueLabel: string
  total: number
  average?: number | null
  maxLabel?: string
  maxValue: number | null
  isPercent?: boolean
}): HTMLElement | undefined {
  return createInsightStrip([
    {
      label: params.isPercent ? `${params.valueLabel}平均值` : params.valueLabel,
      value: formatMetricValue(params.isPercent ? params.average : params.total, {
        isPercent: params.isPercent,
      }),
    },
    {
      label: params.maxLabel ? `最高 ${params.maxLabel}` : '最高值',
      value: formatMetricValue(params.maxValue, { isPercent: params.isPercent }),
    },
  ])
}

export function createCenterLabel(params: {
  title: string
  value: string
  subTitle?: string
}): HTMLElement {
  const wrapper = document.createElement('div')
  Object.assign(wrapper.style, {
    left: '50%',
    top: '50%',
    transform: 'translate(-50%, -50%)',
    textAlign: 'center',
    maxWidth: '120px',
    color: '#1b2a41',
  })

  const value = document.createElement('div')
  value.textContent = params.value
  Object.assign(value.style, {
    fontSize: '16px',
    fontWeight: '700',
    lineHeight: '22px',
    whiteSpace: 'nowrap',
    overflow: 'hidden',
    textOverflow: 'ellipsis',
  })

  const title = document.createElement('div')
  title.textContent = params.title
  Object.assign(title.style, {
    marginTop: '2px',
    color: '#66758f',
    fontSize: '12px',
    fontWeight: '500',
    lineHeight: '16px',
  })

  wrapper.appendChild(value)
  wrapper.appendChild(title)

  if (params.subTitle) {
    const subTitle = document.createElement('div')
    subTitle.textContent = params.subTitle
    Object.assign(subTitle.style, {
      marginTop: '1px',
      color: '#90a0b6',
      fontSize: '11px',
      lineHeight: '14px',
    })
    wrapper.appendChild(subTitle)
  }

  return wrapper
}
