import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import test from 'node:test'
import assert from 'node:assert/strict'

const indexSource = readFileSync(
  fileURLToPath(new URL('./index.vue', import.meta.url)),
  'utf8'
)
const creatorSource = readFileSync(
  fileURLToPath(new URL('./ChatCreator.vue', import.meta.url)),
  'utf8'
)

test('Smart Q&A does not turn datasource request failures into an unbound message', () => {
  assert.match(
    indexSource,
    /try \{\s*await datasourceContext\.loadDatasources\([\s\S]*?\} catch \(error\) \{[\s\S]*?appendDatasourceLoadErrorAnswer\(inputMessage\.value, error\)/
  )
  assert.match(indexSource, /currentRecord\.local_answer = resolveSmartQaErrorMessage\(error, t\)/)
  assert.match(
    indexSource,
    /if \(!selectAssistantDs\.value && datasourceContext\.datasources\.length === 0\) \{\s*appendNoDatasourceAnswer\(inputMessage\.value\)/
  )
})

test('chat datasource selector keeps load errors separate from an empty successful list', () => {
  const showDsSource = creatorSource.slice(
    creatorSource.indexOf('async function showDs()'),
    creatorSource.indexOf('\nfunction hideDs()')
  )
  assert.match(showDsSource, /try \{[\s\S]*?await datasourceContext\.loadDatasources\([\s\S]*?\} catch \(error\) \{[\s\S]*?return\s*\}/)
  const datasourceLoadCatch = showDsSource.slice(
    showDsSource.indexOf('} catch (error) {'),
    showDsSource.indexOf('\n  if (!selectAssistantDs.value', showDsSource.indexOf('} catch (error) {'))
  )
  assert.doesNotMatch(datasourceLoadCatch, /onNoDatasource/)
})
