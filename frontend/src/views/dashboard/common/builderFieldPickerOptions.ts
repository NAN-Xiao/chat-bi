export type FieldOption = {
  label: string
  value: string
  table: string
  tableLabel?: string
  tableReferenceLabel?: string
  tableRole?: string
  fieldRole?: string
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

const OBJECT_GROUP_TABLE_ROLES = new Set([
  'subject',
  'subjectprofile',
  'dailyusersnapshot',
  'user',
  'profile',
  'profiletable',
  'userprofile',
])

const NUMERIC_FIELD_TYPES = new Set([
  'number',
  'numeric',
  'decimal',
  'double',
  'float',
  'int',
  'integer',
  'long',
  'bigint',
  'real',
  '数值',
  '数字',
  '整数',
  '小数',
])

const TIME_FIELD_TYPES = new Set([
  'date',
  'datetime',
  'timestamp',
  'timestamptz',
  'timestampms',
  'time',
  '日期',
  '时间',
])

function normalizeFieldType(value = '') {
  return String(value || '')
    .trim()
    .toLowerCase()
    .replace(/类型$/u, '')
    .replace(/[^a-z0-9\u4e00-\u9fa5]/gu, '')
}

function fieldTypeValues(option: Pick<FieldOption, 'category' | 'semanticType' | 'propertyType' | 'type'>) {
  return [option.category, option.semanticType, option.propertyType, option.type]
    .map((value) => normalizeFieldType(value))
    .filter(Boolean)
}

export function isNumericFieldOption(option: Pick<FieldOption, 'category' | 'semanticType' | 'propertyType' | 'type'>) {
  return fieldTypeValues(option).some((value) => NUMERIC_FIELD_TYPES.has(value))
}

export function isTimeFieldOption(option: Pick<FieldOption, 'category' | 'semanticType' | 'propertyType' | 'type'>) {
  return fieldTypeValues(option).some((value) => TIME_FIELD_TYPES.has(value))
}

function builderTimeFieldPriority(option: FieldOption) {
  const role = normalizeFieldType(option.fieldRole)
  const text = [
    option.label,
    option.displayName,
    option.field,
    option.value,
  ]
    .filter(Boolean)
    .join(' ')
    .toLowerCase()
  if (
    role === 'partitiondate' ||
    /业务日期|分区日期|分区字段|partition[_\s-]*date|partition[_\s-]*field/.test(text)
  ) return 0
  if (/事件日期|event[_\s-]*date/.test(text)) return 1
  if (/事件时间|event[_\s-]*time/.test(text)) return 2
  if (/日期|date|day|dt/.test(text)) return 3
  if (/时间|time|timestamp/.test(text)) return 4
  return 5
}

export function preferredBuilderTimeField(options: FieldOption[]) {
  return options
    .map((option, index) => ({ option, index, priority: builderTimeFieldPriority(option) }))
    .sort((left, right) => left.priority - right.priority || left.index - right.index)[0]?.option.value || ''
}

export function preferredBuilderEntityField(options: FieldOption[]) {
  return options.find((option) => normalizeRole(option.fieldRole) === 'subjectid')?.value || ''
}

function normalizeRole(value = '') {
  return String(value || '')
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9\u4e00-\u9fa5]/gu, '')
}

function isJsonSubfieldOption(option: Pick<FieldOption, 'sourceField' | 'jsonPath' | 'isJsonSubfield'>) {
  return Boolean(option.isJsonSubfield || (option.sourceField && option.jsonPath))
}

export function fieldOptionDisplayName(option?: FieldOption, fallback = '') {
  if (!option) {
    return fallback.split('.').pop() || ''
  }
  if (option.kind === 'tracking-event') {
    return option.displayName || option.label || option.eventName || option.field
  }
  if (
    isJsonSubfieldOption(option) &&
    option.sourceField &&
    option.field.startsWith(`${option.sourceField}.`)
  ) {
    const explicitLabel = option.label && option.label !== option.field ? option.label : ''
    return option.displayName || explicitLabel || option.field.slice(option.sourceField.length + 1)
  }
  return option.displayName || option.label || option.field
}

export function isObjectGroupTableOption(option: Pick<FieldOption, 'tableRole'>) {
  const normalizedRole = normalizeRole(option.tableRole)
  return Boolean(normalizedRole && OBJECT_GROUP_TABLE_ROLES.has(normalizedRole))
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
  return !isObjectGroupTableOption(option) && !isContainerFieldOption(option)
}

export function isTrackingEventPropertyOption(option: FieldOption) {
  return option.kind === 'tracking-property' && isSelectableFieldOption(option)
}

export function isEventUserPropertyOption(option: FieldOption, eventTable = 'event') {
  return (
    option.kind !== 'tracking-property' &&
    option.table === eventTable &&
    normalizeRole(option.sourceField) === 'userinfo' &&
    Boolean(String(option.jsonPath || '').trim()) &&
    isSelectableFieldOption(option)
  )
}

export function propertyAnalysisFieldOptions(input: {
  eventScopeMode?: 'general' | 'event'
  eventScopeActive: boolean
  builderFields: FieldOption[]
  userProperties: FieldOption[]
}) {
  if (input.eventScopeMode === 'event' && !input.eventScopeActive) {
    return []
  }
  if (!input.eventScopeActive) {
    return input.builderFields
  }
  return Array.from(
    new Map(input.userProperties.map((option) => [option.value, option])).values()
  )
}

export function eventScopedPropertyOptions(input: {
  eventOption?: FieldOption
  eventProperties?: FieldOption[]
  userProperties?: FieldOption[]
  activeEventTable?: string
}) {
  const eventTable = input.eventOption?.eventTable || input.eventOption?.table || ''
  if (
    input.eventOption?.kind !== 'tracking-event' ||
    !input.eventOption.eventName ||
    !input.activeEventTable ||
    eventTable !== input.activeEventTable
  ) {
    return []
  }
  const options = [
    ...(input.eventProperties || []),
    ...(input.userProperties || []),
  ]
  const uniqueOptions = new Map<string, FieldOption>()
  options.forEach((option) => {
    if (!uniqueOptions.has(option.value)) {
      uniqueOptions.set(option.value, option)
    }
  })
  return Array.from(uniqueOptions.values())
}

export function eventRelatedPropertyOptions(input: {
  eventOption?: FieldOption
  eventProperties?: FieldOption[]
  allEventProperties?: FieldOption[]
  otherProperties?: FieldOption[]
  activeEventTable?: string
}) {
  const eventTable = input.eventOption?.eventTable || input.eventOption?.table || ''
  const eventName = input.eventOption?.eventName || ''
  if (
    input.eventOption?.kind !== 'tracking-event' ||
    !eventName ||
    !input.activeEventTable ||
    eventTable !== input.activeEventTable
  ) {
    return []
  }
  const eventPropertySourceKeys = new Set(
    (input.allEventProperties || input.eventProperties || [])
      .filter((option) => option.table === eventTable && option.kind === 'tracking-property')
      .flatMap(fieldOptionSourceKeys)
  )
  const options = [
    ...(input.eventProperties || []).filter((option) => (
      option.table === eventTable
      && option.kind === 'tracking-property'
      && option.eventName === eventName
    )),
    ...(input.otherProperties || []).filter((option) => (
      option.table === eventTable
      && option.kind !== 'tracking-event'
      && option.kind !== 'tracking-property'
      && isSelectableFieldOption(option)
      && !fieldOptionSourceKeys(option).some((key) => eventPropertySourceKeys.has(key))
    )),
  ]
  return Array.from(new Map(options.map((option) => [option.value, option])).values())
}

function fieldOptionSourceKeys(option: FieldOption) {
  const table = String(option.table || '').trim().toLowerCase()
  const field = String(option.field || option.propertyName || '').trim().toLowerCase()
  const sourceField = String(option.sourceField || '').trim().toLowerCase()
  const jsonPath = String(option.jsonPath || '').trim().toLowerCase()
  return [
    field ? `${table}:field:${field}` : '',
    sourceField && jsonPath ? `${table}:json:${sourceField}:${jsonPath}` : '',
  ].filter(Boolean)
}
