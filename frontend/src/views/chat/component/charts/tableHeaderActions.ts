export const TABLE_HEADER_ACTION_ICON_THEME = {
  size: 24,
  margin: {
    left: 0,
    right: 4,
  },
} as const

export function resolveTableHeaderActionIconFill(
  _kind: 'filter' | 'sort',
  active: boolean,
  hovering: boolean
) {
  if (hovering) {
    return active ? '#337ecc' : '#606266'
  }
  return active ? '#409eff' : '#909399'
}
