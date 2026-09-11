async (page) => {
  const base = await page.evaluate(() => new URL('/tests/browser/analysis-pickers.html', location.href).href)
  const errors = []
  page.on('pageerror', error => errors.push(error.message))
  const assert = (condition, message) => { if (!condition) throw new Error(message) }
  async function switchModel(label) {
    await page.locator('.analysis-model-select').click()
    await page.getByRole('option', { name: label, exact: true }).click()
  }
  async function assertOnTop() {
    await page.waitForFunction(() => {
      const popups = Array.from(document.querySelectorAll('.builder-field-picker-popper'))
        .filter(element => getComputedStyle(element).display !== 'none')
      return popups.length === 1 && getComputedStyle(popups[0]).opacity === '1'
    })
    const popup = page.locator('.builder-field-picker-popper:visible')
    await popup.waitFor()
    const result = await popup.evaluate(element => {
      const rect = element.getBoundingClientRect()
      return {
        zIndex: getComputedStyle(element).zIndex,
        onTop: element.contains(document.elementFromPoint(rect.x + 20, rect.y + 20)),
      }
    })
    assert(result.onTop, `Picker is obscured at z-index ${result.zIndex}`)
    return result
  }
  const results = []
  for (const width of [1280, 720]) {
    await page.setViewportSize({ width, height: 900 })
    await page.goto(base)
    await page.getByRole('button', { name: 'Close this dialog' }).click()
    // Stage the library's global counter after a long editing session.
    // All opening, switching and selecting assertions below use real clicks.
    await page.evaluate(() => { window._de_elZIndexContextKey_initial = 6000 })
    await page.getByRole('button', { name: 'Open editor', exact: true }).click()
    await page.locator('.analysis-model-select').click()
    const labels = await page.getByRole('option').allTextContents()
    await page.keyboard.press('Escape')
    assert(!labels.some(label => label.trim() === '热力地图'), 'Hidden heatmap option must remain hidden')
    for (const label of labels) {
      await switchModel(label.trim())
      const summary = page.locator('.analysis-model-context')
      const name = summary.locator('.analysis-model-context-name')
      const content = summary.locator('.analysis-model-context-content')
      assert(await summary.count() === 1, 'Expected one shared model summary')
      assert((await name.innerText()).trim() === label.trim(), `Incorrect model name for ${label}`)
      assert(await content.count() === 0, `Model description text must be hidden: ${label}`)
      if (['事件分析', '属性分析', '留存分析', '间隔分析'].includes(label.trim())) {
        await page.screenshot({ path: `output/playwright/model-${label.trim()}-${width}.png` })
      }
      const picker = page.locator('.sql-builder-content .builder-field-picker-trigger').first()
      if (!await picker.count()) continue
      await picker.click()
      const result = await assertOnTop()
      await picker.click()
      results.push({ width, model: label.trim(), descriptionTextHidden: true, ...result })
    }
    await switchModel('漏斗分析')
    await page.locator('.funnel-subject-line .builder-field-picker-trigger').click()
    await assertOnTop()
    await page.getByRole('button', { name: 'entity_id varchar', exact: true }).click()
    assert((await page.locator('.funnel-subject-line').innerText()).includes('entity_id'), 'Subject not selected')
    for (const step of [1, 2, 3]) {
      await page.getByRole('button', { name: `选择步骤${step}事件`, exact: true }).click()
      await assertOnTop()
      await page.getByRole('button', { name: 'Start start', exact: true }).click()
    }
    await page.locator('.funnel-subject-line .builder-field-picker-trigger').click()
    await assertOnTop()
    await page.screenshot({ path: `output/playwright/picker-after-${width}.png` })
    await page.getByRole('button', { name: 'Close this dialog' }).click()
    await page.getByRole('button', { name: 'Open editor', exact: true }).click()
    await switchModel('漏斗分析')
    await page.locator('.funnel-subject-line .builder-field-picker-trigger').click()
    await assertOnTop()
  }
  await page.goto(`${base}?empty`)
  await switchModel('漏斗分析')
  await page.getByRole('button', { name: '选择步骤1事件', exact: true }).click()
  await assertOnTop()
  assert((await page.locator('.builder-field-picker-popper:visible').innerText()).includes('暂无事件'), 'Missing explicit empty state')
  assert(errors.length === 0, errors.join('\n'))
  return { results, emptyState: 'passed', pageErrors: errors }
}
