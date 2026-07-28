export const TABLE_HEADER_ACTION_ICON_THEME = {
  size: 16,
  margin: {
    left: 6,
    right: 2,
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
