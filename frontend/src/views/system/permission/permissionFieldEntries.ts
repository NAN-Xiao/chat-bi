export interface PermissionFieldOption {
  id: number | string
  field_name: string
  field_comment?: string | null
  source_field?: string | null
  json_path?: string | null
  is_json_subfield?: boolean
}

export interface PermissionFieldEntry {
  field_id: number | string
  field_name: string
  field_comment: string
  source_field?: string
  json_path?: string
  is_json_subfield?: true
  enable: boolean
}

export interface PermissionRuleSaveEntry {
  type?: string
  permissions?: PermissionFieldEntry[]
  permission_list?: unknown[]
  expression_tree?: Record<string, unknown>
  [key: string]: unknown
}

const fieldIdKey = (value: number | string): string =>
  `${typeof value}:${String(value)}`

export const fieldOptionsToPermissionEntries = (
  options: PermissionFieldOption[],
  savedEntries: Array<Pick<PermissionFieldEntry, 'field_id' | 'enable'>> = []
): PermissionFieldEntry[] => {
  const enabledById = new Map(
    savedEntries.map((entry) => [fieldIdKey(entry.field_id), entry.enable] as const)
  )
  return options.map((option) => {
    const entry: PermissionFieldEntry = {
      field_id: option.id,
      field_name: option.field_name,
      field_comment: option.field_comment || '',
      enable: enabledById.get(fieldIdKey(option.id)) ?? true,
    }
    if (option.is_json_subfield || (option.source_field && option.json_path)) {
      entry.source_field = option.source_field || ''
      entry.json_path = option.json_path || ''
      entry.is_json_subfield = true
    }
    return entry
  })
}

export const permissionRulesToSaveEntries = (
  entries: PermissionRuleSaveEntry[]
): PermissionRuleSaveEntry[] =>
  entries.map((entry) => {
    const isMetadata = ['schema', 'event', 'event_property'].includes(String(entry.type))
    const { table_id: _tableId, ...withoutTableId } = entry
    return {
      ...(isMetadata ? withoutTableId : entry),
      permissions:
        entry.type === 'column'
          ? (entry.permissions || []).filter((item) => item.enable === false)
          : isMetadata
            ? entry.permissions || []
            : [],
      permission_list: [],
      expression_tree: entry.type === 'row' ? entry.expression_tree || {} : {},
    }
  })

export const sortPermissionEntriesRestrictedFirst = (
  entries: PermissionFieldEntry[]
): PermissionFieldEntry[] =>
  [...entries].sort((left, right) => Number(left.enable) - Number(right.enable))
