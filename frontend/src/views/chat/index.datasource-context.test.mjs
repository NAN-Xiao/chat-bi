import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import test from 'node:test'
import assert from 'node:assert/strict'

const indexSource = readFileSync(fileURLToPath(new URL('./index.vue', import.meta.url)), 'utf8')
const creatorSource = readFileSync(
  fileURLToPath(new URL('./ChatCreator.vue', import.meta.url)),
  'utf8'
)

test('Smart Q&A does not turn datasource request failures into an unbound state', () => {
  const prepareSource = indexSource.slice(
    indexSource.indexOf('const ensureChatReadyForSend = async () =>'),
    indexSource.indexOf('\nconst sendMessage = async')
  )
  assert.match(prepareSource, /try \{[\s\S]*?await datasourceContext\.loadDatasources/)
  assert.match(prepareSource, /catch \(error\) \{[\s\S]*?return false/)
  const catchSource = prepareSource.slice(
    prepareSource.indexOf('catch (error)'),
    prepareSource.indexOf('if (!selectAssistantDs.value && datasourceContext.datasourceId)')
  )
  assert.doesNotMatch(catchSource, /appendNoDatasourceAnswer/)
})

test('the chat datasource selector preserves load failures as errors', () => {
  const showDsSource = creatorSource.slice(
    creatorSource.indexOf('async function showDs()'),
    creatorSource.indexOf('\nfunction hideDs()')
  )
  assert.match(showDsSource, /try \{[\s\S]*?await datasourceContext\.loadDatasources/)
  assert.match(showDsSource, /catch \(error\) \{[\s\S]*?return\s*\}/)
  const catchSource = showDsSource.slice(
    showDsSource.indexOf('catch (error)'),
    showDsSource.indexOf('if (!selectAssistantDs.value && datasourceContext.datasourceId)')
  )
  assert.doesNotMatch(catchSource, /onNoDatasource/)
})
