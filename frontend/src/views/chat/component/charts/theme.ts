import type { G2Spec } from '@antv/g2'

export const chartPalette = [
  '#5d8df7',
  '#45c99a',
  '#f28b70',
  '#f5bf5f',
  '#687e9e',
  '#42bfd4',
  '#7a8fff',
  '#ffad66',
  '#9cb3d2',
  '#2fb47f',
]

export const chartTheme = {
  color: chartPalette[0],
  category10: chartPalette,
  category20: [
    ...chartPalette,
    '#8bb1ff',
    '#75ddb2',
    '#ff9b9b',
    '#ffd37f',
    '#7d8da8',
    '#67d3dc',
    '#a6b3ff',
    '#f5b07f',
    '#b6c6dd',
    '#63c99e',
  ],
  view: {
    viewFill: 'transparent',
    plotFill: 'transparent',
    mainFill: 'transparent',
    contentFill: 'transparent',
  },
  axis: {
    gridLineDash: [2, 6],
    gridLineWidth: 1,
    gridStroke: '#e9f0f8',
    gridStrokeOpacity: 1,
    labelFill: '#7a89a0',
    labelOpacity: 1,
    labelFontSize: 12,
    labelFontWeight: 400,
    labelFontFamily:
      '"Inter", "PingFang SC", "Microsoft YaHei", "Helvetica Neue", Arial, sans-serif',
    line: false,
    tick: false,
    titleFill: '#7a89a0',
    titleFontSize: 12,
  },
  legendCategory: {
    itemLabelFill: '#728198',
    itemLabelFillOpacity: 1,
    itemLabelFontSize: 12,
    itemMarkerSize: 7,
    itemMarkerLineWidth: 0,
    itemSpacing: [6, 12, 6],
    padding: [2, 0, 8, 0],
  },
  legendContinuous: {
    labelFill: '#728198',
    labelFillOpacity: 1,
    handleLabelFill: '#728198',
    handleLabelFillOpacity: 1,
  },
  line: {
    line: {
      strokeOpacity: 1,
      lineWidth: 2.4,
      lineCap: 'round',
      lineJoin: 'round',
    },
  },
  point: {
    point: {
      r: 2.8,
      fillOpacity: 1,
      lineWidth: 1.6,
      stroke: '#ffffff',
    },
  },
  interval: {
    rect: {
      fillOpacity: 0.9,
    },
  },
  cell: {
    rect: {
      fillOpacity: 0.9,
    },
  },
  label: {
    fill: '#52657f',
    fillOpacity: 1,
    fontSize: 12,
    fontWeight: 500,
    fontFamily: '"Inter", "PingFang SC", "Microsoft YaHei", "Helvetica Neue", Arial, sans-serif',
    connectorStroke: '#b7c4d8',
    connectorStrokeOpacity: 1,
  },
  tooltip: {
    css: {
      '.g2-tooltip': {
        'background-color': '#ffffff',
        'border-radius': '10px',
        'border': '1px solid #e7eef7',
        'box-shadow': '0 18px 44px rgba(24, 46, 86, 0.14)',
        color: '#1b2a41',
        'font-family': '"Inter", "PingFang SC", "Microsoft YaHei", "Helvetica Neue", Arial, sans-serif',
        'font-size': '12px',
        'line-height': '18px',
        padding: '8px 10px',
      },
      '.g2-tooltip-title': {
        color: '#5d6e86',
        'font-weight': 500,
      },
      '.g2-tooltip-list-item': {
        gap: '8px',
      },
      '.g2-tooltip-list-item-value': {
        color: '#15233b',
        'font-weight': 600,
      },
    },
  },
} as const

export function withChartThemeOptions(options: G2Spec): G2Spec {
  return {
    ...options,
    marginTop: options.marginTop ?? 8,
    marginRight: options.marginRight ?? 10,
    marginBottom: options.marginBottom ?? 4,
    marginLeft: options.marginLeft ?? 2,
    scale: {
      ...options.scale,
      color: {
        range: chartPalette,
        ...(typeof options.scale?.color === 'object' ? options.scale.color : {}),
      },
    },
  }
}
