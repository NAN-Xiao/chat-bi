export type FieldOption = {
  label: string
  value: string
  table: string
  tableLabel?: string
  field: string
  displayName?: string
  type?: string
  comment?: string
  tableComment?: string
  category?: string
  semanticType?: string
  sourceField?: string
  jsonPath?: string
  expression?: string
  isJsonSubfield?: boolean
  kind?: string
  eventName?: string
  eventCategory?: string
  eventDescription?: string
  collectSide?: string
  eventTable?: string
  eventNameField?: string
  propertyName?: string
  propertyType?: string
}

const CONTAINER_FIELD_TYPES = new Set([
  '对象组',
  '对象',
  '对象数组',
  '数组',
  'json',
  'jsonb',
  'object',
  'objectarray',
  'array',
  'arrayobject',
  'map',
  'dict',
  'dictionary',
  'struct',
  'record',
])

function normalizeFieldType(value = '') {
  return String(value || '')
    .trim()
    .toLowerCase()
    .replace(/类型$/u, '')
    .replace(/[^a-z0-9\u4e00-\u9fa5]/gu, '')
}

function isJsonSubfieldOption(option: Pick<FieldOption, 'sourceField' | 'jsonPath' | 'isJsonSubfield'>) {
  return Boolean(option.isJsonSubfield || (option.sourceField && option.jsonPath))
}

export function isContainerFieldOption(option: Pick<FieldOption, 'type' | 'semanticType' | 'sourceField' | 'jsonPath' | 'isJsonSubfield'>) {
  if (isJsonSubfieldOption(option)) {
    return false
  }
  const normalizedType = normalizeFieldType(option.semanticType || option.type)
  if (!normalizedType) {
    return false
  }
  return (
    CONTAINER_FIELD_TYPES.has(normalizedType) ||
    normalizedType.includes('对象组') ||
    normalizedType.includes('objectarray') ||
    normalizedType.includes('json')
  )
}

export function isSelectableFieldOption(option: FieldOption) {
  return !isContainerFieldOption(option)
}
