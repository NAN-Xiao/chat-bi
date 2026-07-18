import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const currentDir = dirname(fileURLToPath(import.meta.url))
const tenantView = readFileSync(join(currentDir, 'Tenant.vue'), 'utf8')
const tenantApi = readFileSync(join(currentDir, '../../../api/tenant.ts'), 'utf8')
const locales = {
  zhCN: JSON.parse(readFileSync(join(currentDir, '../../../i18n/zh-CN.json'), 'utf8')),
  zhTW: JSON.parse(readFileSync(join(currentDir, '../../../i18n/zh-TW.json'), 'utf8')),
  en: JSON.parse(readFileSync(join(currentDir, '../../../i18n/en.json'), 'utf8')),
  koKR: JSON.parse(readFileSync(join(currentDir, '../../../i18n/ko-KR.json'), 'utf8')),
}

assert.deepEqual(
  {
    zhCN: locales.zhCN.tenant.roi_datasource,
    zhTW: locales.zhTW.tenant.roi_datasource,
    en: locales.en.tenant.roi_datasource,
    koKR: locales.koKR.tenant.roi_datasource,
  },
  {
    zhCN: 'ROI数据源',
    zhTW: 'ROI 資料來源',
    en: 'ROI data source',
    koKR: 'ROI 데이터 소스',
  }
)
assert.ok(Object.values(locales).every((locale) => locale.tenant.select_roi_datasource))
assert.match(tenantApi, /roi_datasource_id\?: number \| string \| null/)
assert.match(tenantApi, /roi_datasource_name\?: string \| null/)
assert.match(tenantApi, /add: \(data: \{[\s\S]*roi_datasource_id\?: number \| string \| null/)
assert.match(tenantApi, /edit: \([\s\S]*roi_datasource_id\?: number \| string \| null/)
assert.match(tenantView, /v-model="form\.roi_datasource_id"/)
assert.match(tenantView, /clearable/)
assert.match(tenantView, /filterable/)
assert.match(tenantView, /:disabled="isDefaultTenantForm"/)
assert.match(tenantView, /v-for="datasource in datasourceOptions"/)
assert.match(tenantView, /roi_datasource_id: form\.roi_datasource_id \|\| null/)
assert.match(tenantView, /const normalizeRoiDatasourceId = \(tenant\?: TenantInfo \| null\) => tenant\?\.roi_datasource_id \|\| ''/)
assert.match(tenantView, /roi_datasource_id: normalizeRoiDatasourceId\(tenant\)/)
assert.ok(
  tenantView.indexOf("t('tenant.bound_datasource')") <
    tenantView.indexOf("t('tenant.roi_datasource')") &&
    tenantView.indexOf("t('tenant.roi_datasource')") <
      tenantView.indexOf("t('tenant.bound_external_mcp')"),
  'ROI 数据源必须位于普通数据源和第三方 MCP 之间'
)
assert.doesNotMatch(tenantView, /prop="roi_datasource_id"/)
