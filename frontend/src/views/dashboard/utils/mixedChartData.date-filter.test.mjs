import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'

const source = readFileSync(fileURLToPath(new URL('./mixedChartData.ts', import.meta.url)), 'utf8')

assert.match(source, /date_filter:\s*buildDashboardDateFilterRequestForRefresh\(viewInfo\)/)
assert.match(source, /datasource:\s*viewInfo\.datasource/)
assert.doesNotMatch(source, /sourceSql\.datasource\s*\|\|\s*viewInfo\.datasource/)
assert.match(source, /function mixedChartDatasourceFailure\(viewInfo: any\)/)
assert.match(source, /dashboard_chart_datasource_conflict/)
assert.match(source, /if \(mixedChartDatasourceFailure\(viewInfo\)\) \{\s*return false/)
assert.match(source, /const datasourceFailure = mixedChartDatasourceFailure\(viewInfo\)/)
