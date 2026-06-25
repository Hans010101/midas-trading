/**
 * X 营销自动化 · 阶段1 截图 POC
 *
 * 用 Playwright headless Chromium 打开【公开】crypto 详情页,截取「主图卡」
 * (K线 + 布林 + MACD副图 + 缠论标注 · 到 MACD 结束),不含右栏 AI 决策卡 / 策略清单。
 *
 * ★资源受限纪律(VPS 总7.1G/可用2.8G/swap4G):
 *   - 串行:一次只开一个 browser,绝不并发
 *   - 每个 symbol 截完【立即 browser.close()】释放内存(防泄漏)
 *   - --disable-dev-shm-usage:Docker /dev/shm 默认仅 64M,canvas 渲染会爆 → 改用 /tmp
 *   - --no-sandbox:容器内 root 跑 headless 需要(VPS 容器场景)
 *
 * 用法:node apps/web/scripts/x-screenshot-poc.mjs [SYMBOL1 SYMBOL2 ...]
 * 默认截 BTCUSDT / ETHUSDT / SIRENUSDT(主流 + 主流 + 小币/做T热门)。
 */
import { mkdirSync } from 'node:fs'
import { chromium } from 'playwright'

const SYMBOLS = process.argv.slice(2).length ? process.argv.slice(2) : ['BTCUSDT', 'ETHUSDT', 'SIRENUSDT']
const BASE = 'https://midastrade.asia/crypto-preview?symbol='
const OUT = process.env.X_POC_OUT || '/tmp/x-poc'
// 主图卡:含「布林带 + MACD + 缠论」标题的 rounded-lg 卡(右栏 AI 卡/策略清单天然在此卡之外)
const CARD_TEXT = '布林带 + MACD + 缠论'

mkdirSync(OUT, { recursive: true })

for (const sym of SYMBOLS) {
  const t0 = Date.now()
  // ★单实例:每币新开,截完即关 → 内存不累积
  const browser = await chromium.launch({
    headless: true,
    args: ['--no-sandbox', '--disable-dev-shm-usage', '--disable-gpu'],
  })
  try {
    const page = await browser.newPage({
      viewport: { width: 1280, height: 1000 }, // lg 断点 → 桌面布局(主图在左栏宽列)
      deviceScaleFactor: 2, // 2x → 适合 X 推文清晰度
    })
    await page.goto(BASE + sym, { waitUntil: 'networkidle', timeout: 60_000 })
    const card = page.locator('div.rounded-lg').filter({ hasText: CARD_TEXT }).first()
    await card.waitFor({ state: 'visible', timeout: 30_000 })
    // canvas 渲染时机:等卡内 canvas 出现 + 额外结算时间(K线/布林/缠论画完,不截空白半成品)
    await card.locator('canvas').first().waitFor({ state: 'visible', timeout: 30_000 })
    await page.waitForTimeout(2_500)
    await card.screenshot({ path: `${OUT}/${sym}.png` })
    console.log(`✓ ${sym}  ${Date.now() - t0}ms  → ${OUT}/${sym}.png`)
  } catch (e) {
    console.log(`✗ ${sym}  FAIL: ${e.message}`)
  } finally {
    await browser.close() // ★关键:释放内存
  }
}
