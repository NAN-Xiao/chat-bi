async (page) => {
  const checks = []
  const assert = (value, message) => {
    if (!value) throw Error(message)
    checks.push(message)
  }
  await page.waitForFunction(
    () =>
      window.cardChromeQA && document.querySelectorAll('.chart-render-layer--active').length === 5
  )
  const initial = await page.evaluate(() => JSON.stringify(cardChromeQA.views))
  for (const theme of ['dark', 'light', 'dark']) {
    await page.evaluate((t) => cardChromeQA.applyTheme(t), theme)
    await page.getByRole('heading').hover()
    await page.evaluate(async () => {
      await Promise.all(document.getAnimations().map((a) => a.finished.catch(() => {})))
    })
    const state = await page.evaluate(() => {
      const outer = document.querySelector('[data-fixture="framed"]'),
        inner = outer.querySelector('.chart-base-container'),
        range = outer.querySelector('.date-expression-range'),
        trigger = outer.querySelector('.date-expression-trigger')
      const css = (e) => {
        const s = getComputedStyle(e)
        return {
          border: s.borderTopWidth,
          borderColor: s.borderTopColor,
          radius: s.borderTopLeftRadius,
          background: s.backgroundColor,
          shadow: s.boxShadow,
        }
      }
      return {
        outer: css(outer),
        inner: css(inner),
        range: css(range),
        trigger: css(trigger),
        date: range.textContent,
        preset: trigger.querySelector('.date-expression-label').textContent,
        frameless: css(document.querySelector('[data-fixture="frameless"]')),
        tabCard: css(document.querySelector('[data-fixture="frameless"] .chart-base-container')),
        standalone: css(
          document.querySelector('[data-fixture="standalone"] .chart-base-container')
        ),
        legacy: css(document.querySelector('[data-fixture="legacy"] .date-filter-trigger')),
        editor: css(
          document.querySelector('[data-fixture="editor-picker"] .date-expression-range')
        ),
        editorCard: css(document.querySelector('[data-fixture="editor-card"] .item-content')),
        editorChart: css(document.querySelector('[data-fixture="editor-card"] .chart-base-container')),
      }
    })
    assert(
      state.outer.borderColor === (theme === 'dark' ? 'rgb(57, 69, 86)' : 'rgb(232, 237, 245)') &&
        state.outer.border === '1px' &&
        state.outer.radius === '8px' &&
        state.outer.shadow === 'none',
      theme + ' single subtle card outline'
    )
    assert(
      state.editorCard.borderColor === state.outer.borderColor &&
        state.editorCard.radius === state.outer.radius &&
        state.editorCard.shadow === 'none' && state.editorCard.border === '1px' &&
        state.editorChart.border === '0px',
      theme + ' editor and preview share a single card outline even while selected'
    )
    assert(
      state.inner.border === '0px' &&
        state.frameless.border === '0px' &&
        state.tabCard.border === '1px' &&
        state.standalone.border === '1px',
      theme + ' framed, frameless and standalone each draw exactly one outline'
    )
    assert(
      state.range.border === '0px' &&
        state.range.background === 'rgba(0, 0, 0, 0)' &&
        state.trigger.border === '0px' &&
        state.trigger.background === 'rgba(0, 0, 0, 0)',
      theme + ' inline dates have no badge or button box'
    )
    assert(
      state.legacy.border === '0px' &&
        state.legacy.background === 'rgba(0, 0, 0, 0)' &&
        state.editor.border === '1px',
      theme + ' legacy card trigger matches and editor retains control appearance'
    )
    assert(
      state.date === '2026-08-29 至 2026-09-27' && state.preset === '过去30天',
      theme + ' resolved range and configured preset preserved'
    )
  }
  for (const width of [680, 340, 300, 260]) {
    await page.evaluate((w) => (cardChromeQA.width.value = w), width)
    await page.waitForFunction(
      (w) =>
        Math.abs(
          document.querySelector('[data-fixture="framed"]').getBoundingClientRect().width - w
        ) < 1,
      width
    )
    const rows = await page.locator('.cards .date-expression-toolbar').evaluateAll((toolbars) =>
      toolbars.map((t) => {
        const card = t.closest('.chart-base-container'),
          button = t.querySelector('button'),
          text = button.querySelector(':scope > span'),
          range = t.querySelector('.date-expression-range')
        const r = button.getBoundingClientRect(),
          bounds = card.getBoundingClientRect(),
          next = card.querySelector('.chart-show-area').getBoundingClientRect(),
          style = getComputedStyle(card)
        return {
          right: r.right <= bounds.right,
          left: r.left >= bounds.left,
          noOverlap: text.getBoundingClientRect().bottom <= next.top + 1,
          aligned:
            Math.abs(
              r.right -
                (bounds.right - parseFloat(style.paddingRight) - parseFloat(style.borderRightWidth))
            ) < 2,
          fullRangeTitle: range.title === '2026-08-29 至 2026-09-27',
        }
      })
    )
    assert(
      rows.every((r) => r.right && r.left && r.noOverlap && r.aligned && r.fullRangeTitle),
      'date layout remains usable at width ' + width
    )
  }
  await page.evaluate(() => (cardChromeQA.width.value = 340))
  const trigger = page.locator('[data-fixture="framed"] .date-expression-trigger')
  await trigger.focus()
  await page.keyboard.press('Enter')
  await page.locator('.dashboard-date-expression-popper:visible').waitFor()
  await page
    .locator('.dashboard-date-expression-popper:visible')
    .getByRole('button', { name: '过去7天', exact: true })
    .click()
  await page
    .locator('.dashboard-date-expression-popper:visible')
    .getByRole('button', { name: '取消', exact: true })
    .click()
  await page.locator('.dashboard-date-expression-popper:visible').waitFor({ state: 'hidden' })
  assert(
    (await page.evaluate(() => JSON.stringify(cardChromeQA.views))) === initial,
    'cancel preserves date settings and chart data'
  )
  await page.evaluate(() => (cardChromeQA.showRange.value = false))
  assert(
    (await page.locator('[data-fixture="inline-picker"] .date-expression-range').count()) === 0,
    'preset-only control stays supported'
  )
  await page.evaluate(() => {
    cardChromeQA.showRange.value = true
    cardChromeQA.disabled.value = true
  })
  assert(
    await page.locator('[data-fixture="inline-picker"] button').isDisabled(),
    'disabled control remains disabled'
  )
  await page.getByRole('heading').hover()
  await page
    .locator('[data-fixture="framed"]')
    .screenshot({ path: '.playwright-cli/reference-date-border-dark.png' })
  await page.evaluate(() => {
    cardChromeQA.width.value = 260
    Object.assign(cardChromeQA.views[1].dateFilter.expression, {
      mode: 'range',
      start: { mode: 'static', date: '2026-08-29' },
      end: { mode: 'static', date: '2026-09-27' },
    })
  })
  await page.waitForFunction(
    () =>
      document.querySelector('[data-fixture="frameless"] .date-expression-label').textContent ===
      '2026-08-29 至 2026-09-27'
  )
  assert(
    await page.locator('.cards .date-expression-toolbar').evaluateAll((ts) =>
      ts.every((t) => {
        const b = t.querySelector('button'),
          s = b.querySelector(':scope > span').getBoundingClientRect(),
          card = t.closest('.chart-base-container')
        return (
          b.scrollWidth <= b.clientWidth &&
          s.bottom <= card.querySelector('.chart-show-area').getBoundingClientRect().top + 1
        )
      })
    ),
    'custom static range fits narrow main and Tab cards'
  )
  return { passed: checks.length, checks }
}
