import assert from 'node:assert/strict'

const {
  createPermissionDeniedChartRegistry,
  dashboardCacheRefreshDisposition,
  isPermissionDeniedRefreshResult,
  shouldRetryDashboardChartFailure,
} = await import('./dashboardPermissionRefresh.ts')

const deniedEntry = { component: { id: 101 }, viewInfo: {} }
const allowedEntry = { component: { id: 102 }, viewInfo: {} }
const registry = createPermissionDeniedChartRegistry()
const independentRegistry = createPermissionDeniedChartRegistry()

registry.mark(deniedEntry)
assert.equal(registry.has(deniedEntry), true, '当前页面应记住已拒绝图表')
assert.equal(registry.has(allowedEntry), false, '未拒绝图表不应被误过滤')
assert.equal(independentRegistry.has(deniedEntry), false, '不同页面实例不能共享权限拒绝状态')
assert.deepEqual(
  [deniedEntry, allowedEntry].filter((entry) => !registry.has(entry)),
  [allowedEntry],
  '自动刷新候选应排除已拒绝图表'
)

registry.mark({ component: {}, viewInfo: {} })
assert.equal(registry.has({ component: {}, viewInfo: {} }), false, '缺少组件 ID 时不能创建错误终止状态')

registry.reset()
assert.equal(registry.has(deniedEntry), false, '完整加载后应允许图表重新判权')

const permissionDenied = { status: 'failed', error_type: 'permission_denied' }
assert.equal(isPermissionDeniedRefreshResult(permissionDenied), true)
assert.equal(
  dashboardCacheRefreshDisposition(permissionDenied, false),
  'permission_denied',
  '缓存层已经拒绝权限时不能继续查询数据库'
)
assert.equal(
  dashboardCacheRefreshDisposition({ status: 'failed', error_type: 'dashboard_cache_miss' }, false),
  'refresh_database',
  '缓存未命中仍应查询数据库'
)
assert.equal(
  dashboardCacheRefreshDisposition({ status: 'success', data: [] }, false),
  'refresh_database',
  '缓存没有可用快照时仍应查询数据库'
)
assert.equal(
  dashboardCacheRefreshDisposition({ status: 'success', data: [{ value: 1 }] }, true),
  'ready',
  '可用缓存结果应直接展示'
)

assert.equal(
  shouldRetryDashboardChartFailure(permissionDenied, false),
  false,
  '权限拒绝不能进入短时失败重试'
)
assert.equal(
  shouldRetryDashboardChartFailure({ status: 'failed', error_type: 'dashboard_query_busy' }, false),
  true,
  '查询繁忙且没有快照时应保留原有短时重试'
)
assert.equal(
  shouldRetryDashboardChartFailure({ status: 'failed', error_type: 'query_failed' }, true),
  false,
  '已有快照的普通失败不需要短时重试'
)
assert.equal(
  shouldRetryDashboardChartFailure({ status: 'success' }, false),
  false,
  '成功结果不能进入失败重试'
)
