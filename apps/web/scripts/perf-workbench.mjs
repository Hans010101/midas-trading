/**
 * Task 3 I3:工作台性能基准。
 *
 * 用浏览器 Performance Timing API 直读真实指标:
 *   - 初次渲染:navigation domContentLoaded / loadEventEnd
 *   - /api/v1/market/kline API 调用 RTT
 *   - 周期切换 + 市场切换的端到端 click→新数据 RTT
 *
 * 注:klinecharts 把 "Time:" 等 info 写在 canvas 上(不进 DOM),
 * 所以这里不用 innerText 等待 chart ready,而是 wait 网络事件。
 */

import { chromium } from 'playwright'

const URL = process.env.WORKBENCH_URL ?? 'http://localhost:3000/workbench'

async function waitForKlineApi(page) {
  return await page.waitForResponse(
    (r) => r.url().includes('/api/v1/market/kline') && r.status() === 200,
    { timeout: 15_000 },
  )
}

async function timeOp(label, fn) {
  const t0 = Date.now()
  await fn()
  const elapsed = Date.now() - t0
  console.log(`${label}: ${elapsed}ms`)
  return elapsed
}

async function main() {
  const browser = await chromium.launch()
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } })
  const page = await ctx.newPage()

  // ============ Op 1:初次渲染 ============
  console.log('=== Op 1:初次渲染(/workbench cold load + 第一帧 K 线 API 响应)===')
  const t0 = Date.now()
  const navPromise = page.goto(URL, { waitUntil: 'domcontentloaded' })
  const apiPromise = waitForKlineApi(page)
  await Promise.all([navPromise, apiPromise])
  // 给 klinecharts canvas paint 一帧
  await page.waitForTimeout(200)
  const initialMs = Date.now() - t0
  console.log(`初次渲染端到端: ${initialMs}ms`)

  // 读浏览器 nav timing
  const timing = await page.evaluate(() => {
    const nav = performance.getEntriesByType('navigation')[0]
    const resources = performance
      .getEntriesByType('resource')
      .filter((r) => r.name.includes('/market/kline'))
      .map((r) => ({ url: r.name.split('?')[1] ?? r.name, duration: Math.round(r.duration) }))
    return {
      domContentLoaded: Math.round(nav.domContentLoadedEventEnd),
      loadEnd: Math.round(nav.loadEventEnd),
      apiCalls: resources,
    }
  })
  console.log(`  DOMContentLoaded: ${timing.domContentLoaded}ms`)
  console.log(`  loadEventEnd:     ${timing.loadEnd}ms`)
  console.log(`  /market/kline calls:`)
  for (const c of timing.apiCalls) console.log(`    ${c.duration}ms · ${c.url}`)

  // 确保停在 crypto BTC 1d
  await page.locator('nav button:has-text("加密")').first().click()
  await page.locator('button:has-text("日 K")').first().click()
  await waitForKlineApi(page).catch(() => null) // 可能命中缓存(无 response)
  await page.waitForTimeout(500)

  // ============ Op 2:周期切换(测 3 个切换) ============
  console.log('\n=== Op 2:周期切换(crypto BTC,1d → 15m → 1h → 1d)===')
  const periodSwitches = [
    { from: '1d', to: '15 分', tag: '1d→15m' },
    { from: '15 分', to: '1 小时', tag: '15m→1h' },
    { from: '1 小时', to: '日 K', tag: '1h→1d' },
  ]
  const periodTimes = []
  for (const sw of periodSwitches) {
    const t = await timeOp(`  ${sw.tag}`, async () => {
      const apiP = page.waitForResponse(
        (r) => r.url().includes('/market/kline'),
        { timeout: 600 },
      ).catch(() => null)
      await page.locator(`button:has-text("${sw.to}")`).first().click()
      await apiP
      await page.waitForTimeout(150)
    })
    periodTimes.push(t)
  }

  // ============ Op 3:市场切换(crypto → us → cn → crypto) ============
  console.log('\n=== Op 3:市场切换(联动默认 symbol)===')
  const marketSwitches = [
    { to: '美股', tag: 'crypto→us' },
    { to: 'A 股', tag: 'us→cn' },
    { to: '加密', tag: 'cn→crypto' },
  ]
  const marketTimes = []
  for (const sw of marketSwitches) {
    const t = await timeOp(`  ${sw.tag}`, async () => {
      const apiP = page.waitForResponse(
        (r) => r.url().includes('/market/kline'),
        { timeout: 600 },
      ).catch(() => null)
      await page.locator(`nav button:has-text("${sw.to}")`).first().click()
      await apiP
      await page.waitForTimeout(150)
    })
    marketTimes.push(t)
  }

  await ctx.close()
  await browser.close()

  console.log('\n=== 汇总 ===')
  console.log(`初次渲染:       ${initialMs}ms`)
  console.log(`周期切换 avg:    ${Math.round(periodTimes.reduce((a, b) => a + b, 0) / periodTimes.length)}ms (samples ${periodTimes.join('/')})`)
  console.log(`市场切换 avg:    ${Math.round(marketTimes.reduce((a, b) => a + b, 0) / marketTimes.length)}ms (samples ${marketTimes.join('/')})`)
}

main().catch((e) => {
  console.error(e)
  process.exit(1)
})
