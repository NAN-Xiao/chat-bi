import type { FieldOption } from './builderFieldPickerOptions'

type MetadataCacheKeyInput = {
  datasourceId?: number | string | null
  tenantId?: number | string | null
}

type MetadataCacheEntry<T> = {
  value?: T
  promise?: Promise<T>
}

type TrackingEventCatalogProperty = {
  value: string
  property_name: string
  display_name: string
  property_type: string
  source_field: string
  json_path: string
  description: string
  event_name: string
  event_table: string
  event_name_field: string
}

type TrackingEventCatalogItem = {
  value: string
  event_name: string
  display_name: string
  category: string
  description: string
  event_table: string
  event_name_field: string
  properties: TrackingEventCatalogProperty[]
}

type TrackingEventCatalogGroup = {
  label: string
  value: string
  events: TrackingEventCatalogItem[]
}

type TrackingEventCatalog = {
  tenant_id?: number | string | null
  datasource_id?: number | string | null
  event_table: string
  event_name_field: string
  groups: TrackingEventCatalogGroup[]
}

export type DashboardBuilderEventScope = {
  mode: 'general' | 'event'
  status: 'general' | 'active' | 'missing-default-table' | 'datasource-mismatch' | 'table-unavailable'
  defaultEventTable: string
  message: string
}

const metadataCache = new Map<string, MetadataCacheEntry<any>>()

function stableText(value: any) {
  return value === undefined || value === null || value === '' ? '' : String(value)
}

function plainText(value: any) {
  return stableText(value).trim()
}

function firstPlainText(...values: any[]) {
  for (const value of values) {
    const text = plainText(value)
    if (text) {
      return text
    }
  }
  return ''
}

function eventNamesFromMapping(mapping: any): string[] {
  const names = [
    plainText(mapping?.event_name),
    plainText(mapping?.eventName),
    plainText(mapping?.name),
    plainText(mapping?.value),
  ]
  const events = Array.isArray(mapping?.events) ? mapping.events : []
  events.forEach((event: any) => {
    const text = plainText(event)
    if (text) {
      names.push(text)
    }
  })
  return Array.from(new Set(names.filter(Boolean)))
}

function trackingEventProperties(
  mapping: any,
  eventTable: string,
  eventNameField: string,
  eventName: string
): TrackingEventCatalogProperty[] {
  const properties = Array.isArray(mapping?.properties) ? mapping.properties : []
  const seen = new Set<string>()
  return properties.flatMap((item: any) => {
    const propertyName = firstPlainText(item?.property_name, item?.propertyName, item?.field_name, item?.fieldName, item?.name)
    if (!propertyName || seen.has(propertyName)) {
      return []
    }
    seen.add(propertyName)
    const propertyType = firstPlainText(item?.property_type, item?.propertyType, item?.semantic_type, item?.semanticType, item?.field_type, item?.fieldType, item?.type)
    return [{
      value: item?.value || `tracking-property:${eventTable}.${eventNameField}:${eventName}:${propertyName}`,
      property_name: propertyName,
      display_name: firstPlainText(item?.property_display_name, item?.propertyDisplayName, item?.display_name, item?.displayName, item?.label, propertyName),
      property_type: propertyType,
      source_field: plainText(item?.source_field || item?.sourceField),
      json_path: plainText(item?.json_path || item?.jsonPath),
      description: firstPlainText(item?.description, item?.ai_notes, item?.aiNotes),
      event_name: eventName,
      event_table: eventTable,
      event_name_field: eventNameField,
    }]
  })
}

export function buildDashboardBuilderMetadataCacheKey(input: MetadataCacheKeyInput) {
  return `${stableText(input.tenantId) || 'global'}:${stableText(input.datasourceId) || 'none'}`
}

export async function getCachedDashboardBuilderMetadata<T>(
  key: string,
  loader: () => Promise<T>,
  isCachedValueValid: (value: T) => boolean = () => true
): Promise<T> {
  const cached = metadataCache.get(key)
  if (cached?.value !== undefined) {
    if (isCachedValueValid(cached.value as T)) {
      return cached.value as T
    }
    metadataCache.delete(key)
  }
  if (cached?.promise) {
    return cached.promise as Promise<T>
  }
  const entry: MetadataCacheEntry<T> = {}
  entry.promise = loader()
    .then((value) => {
      entry.value = value
      entry.promise = undefined
      return value
    })
    .catch((error) => {
      metadataCache.delete(key)
      throw error
    })
  metadataCache.set(key, entry)
  return entry.promise
}

export function clearDashboardBuilderMetadataCache(key?: string) {
  if (key) {
    metadataCache.delete(key)
    return
  }
  metadataCache.clear()
}

export function resolveDashboardBuilderEventScope(input: {
  config?: any
  datasourceId?: number | string | null
  tableNames?: string[]
}): DashboardBuilderEventScope {
  const config = input.config
  const defaultEventTable = firstPlainText(config?.default_event_table, config?.defaultEventTable)
  const hasPersistedConfig = Boolean(
    config && (
      config.id
      || defaultEventTable
      || firstPlainText(config.default_event_name_field, config.defaultEventNameField)
      || (Array.isArray(config.event_name_mappings) && config.event_name_mappings.length)
      || (Array.isArray(config.eventNameMappings) && config.eventNameMappings.length)
    )
  )
  if (!hasPersistedConfig || config?.enabled === false) {
    return { mode: 'general', status: 'general', defaultEventTable: '', message: '' }
  }
  if (!defaultEventTable) {
    return {
      mode: 'event',
      status: 'missing-default-table',
      defaultEventTable: '',
      message: '当前工作空间未配置默认事件表，事件配置不可用。',
    }
  }
  const configuredDatasourceId = stableText(config.datasource_id ?? config.datasourceId)
  const currentDatasourceId = stableText(input.datasourceId)
  if (configuredDatasourceId && currentDatasourceId && configuredDatasourceId !== currentDatasourceId) {
    return {
      mode: 'event',
      status: 'datasource-mismatch',
      defaultEventTable,
      message: '当前埋点配置与图表数据源不一致，事件配置不可用。',
    }
  }
  const tableNames = new Set((input.tableNames || []).map(plainText).filter(Boolean))
  if (!tableNames.has(defaultEventTable)) {
    return {
      mode: 'event',
      status: 'table-unavailable',
      defaultEventTable,
      message: `默认事件表 ${defaultEventTable} 不存在或不可访问，事件配置不可用。`,
    }
  }
  return { mode: 'event', status: 'active', defaultEventTable, message: '' }
}

export function getEventScopedFields<T extends Pick<FieldOption, 'table'>>(
  fields: T[],
  scope: DashboardBuilderEventScope
): T[] {
  if (scope.mode === 'general') {
    return [...fields]
  }
  if (scope.status !== 'active') {
    return []
  }
  return fields.filter((field) => field.table === scope.defaultEventTable)
}

export function buildTrackingEventCatalogFromConfig(config: any): TrackingEventCatalog | null {
  if (!config || config.enabled === false) {
    return null
  }
  const eventTable = firstPlainText(config.default_event_table, config.defaultEventTable)
  const eventNameField = firstPlainText(config.default_event_name_field, config.defaultEventNameField)
  if (!eventTable || !eventNameField) {
    return null
  }
  const groups = new Map<string, TrackingEventCatalogGroup>()
  const mappings = Array.isArray(config.event_name_mappings)
    ? config.event_name_mappings
    : Array.isArray(config.eventNameMappings)
      ? config.eventNameMappings
      : []
  mappings.forEach((mapping: any) => {
    if (!mapping || typeof mapping !== 'object') {
      return
    }
    const category = firstPlainText(mapping.event_category, mapping.eventCategory, mapping.category, mapping.metric) || '默认分组'
    const group = groups.get(category) || { label: category, value: category, events: [] }
    eventNamesFromMapping(mapping).forEach((eventName) => {
      if (group.events.some((item) => item.event_name === eventName)) {
        return
      }
      group.events.push({
        value: mapping.value || `tracking-event:${eventTable}.${eventNameField}:${eventName}`,
        event_name: eventName,
        display_name: firstPlainText(mapping.event_display_name, mapping.eventDisplayName, mapping.display_name, mapping.displayName, mapping.metric, mapping.name, eventName),
        category,
        description: firstPlainText(mapping.description, mapping.event_description, mapping.eventDescription, mapping.ai_notes, mapping.aiNotes),
        event_table: eventTable,
        event_name_field: eventNameField,
        properties: trackingEventProperties(mapping, eventTable, eventNameField, eventName),
      })
    })
    groups.set(category, group)
  })
  return {
    tenant_id: config.tenant_id ?? config.tenantId ?? null,
    datasource_id: config.datasource_id ?? config.datasourceId ?? null,
    event_table: eventTable,
    event_name_field: eventNameField,
    groups: Array.from(groups.values()),
  }
}

export function createFieldOptionIndex(input: {
  trackingEventOptions: FieldOption[]
  trackingEventPropertyOptions: FieldOption[]
  schemaFieldOptions: FieldOption[]
}) {
  const byValue = new Map<string, FieldOption>()
  const bySchemaField = new Map<string, FieldOption>()
  ;[
    input.trackingEventOptions,
    input.trackingEventPropertyOptions,
    input.schemaFieldOptions,
  ].forEach((options) => {
    options.forEach((option) => {
      if (option.value && !byValue.has(option.value)) {
        byValue.set(option.value, option)
      }
    })
  })
  input.schemaFieldOptions.forEach((option) => {
    if (option.field && !bySchemaField.has(option.field)) {
      bySchemaField.set(option.field, option)
    }
  })
  return {
    find(value: string) {
      if (!value) {
        return undefined
      }
      return byValue.get(value) || bySchemaField.get(value)
    },
  }
}
