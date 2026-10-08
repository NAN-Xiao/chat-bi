import type { ThemeCfg } from '@antv/s2'
export function getTableTheme(mount: Element): ThemeCfg {
  const style = getComputedStyle(mount)
  const c = (key: string) => style.getPropertyValue(`--workspace-${key}`).trim()
  const cell = (header: boolean) => ({
    cell: {
      backgroundColor: c(header ? 'control-bg' : 'card-bg'),
      crossBackgroundColor: c('card-bg'),
      horizontalBorderColor: c('border'),
      verticalBorderColor: c('border'),
      interactionState: {
        hover: { backgroundColor: c('control-hover-bg'), backgroundOpacity: 1 },
        selected: { backgroundColor: c('active-bg'), backgroundOpacity: 1 },
        hoverFocus: { backgroundColor: c('control-hover-bg'), backgroundOpacity: 1 },
        prepareSelect: { backgroundColor: c('active-bg'), backgroundOpacity: 1 },
      },
    },
    text: { fill: c('text-primary'), fontSize: 12, fontWeight: header ? 600 : 400 },
    bolderText: { fill: c('text-primary') },
    icon: { size: 16, margin: { left: 6, right: 2 }, fill: c('text-secondary') },
  })
  return {
    theme: {
      background: { color: c('card-bg') },
      colCell: cell(true),
      cornerCell: cell(true),
      rowCell: cell(true),
      dataCell: cell(false),
      splitLine: { horizontalBorderColor: c('border'), verticalBorderColor: c('border') },
      scrollBar: { thumbColor: c('text-tertiary'), trackColor: c('control-bg') },
    },
  }
}
