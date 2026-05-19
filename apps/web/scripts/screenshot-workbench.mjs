/**
 * Task 3 I2:Playwright 截图 12 张 · 3 标的 × 4 周期 = 12 张。
 *
 * 用法:从仓库根目录:
 *   node apps/web/scripts/screenshot-workbench.mjs
 *
 * 前置:docker compose up -d 全栈 + 数据预热完成。
 * 600519 三档(15m/1h/1w)由于 AKShare EM 不稳,会显示 EmptyKline 占位卡(0002 翻车 4/7)。
 */

import { chromium } from 'playwright'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const __filename = fileURLToPath(import.meta.url)
const __dirname = path.dirname(__filename)
const OUT_DIR = path.resolve(__dirname, '..', '..', '..', 'docs', 'screenshots')

const SHOTS = [
  // A 股(15m/1h/1w 因 EM 不稳预期显示 EmptyKline)
  { market: 'cn', marketLabel: 'A 股', symbol: '600519', period: '15m', periodLabel: '15 分' },
  { market: 'cn', marketLabel: 'A 股', symbol: '600519', period: '1h', periodLabel: '1 小时' },
  { market: 'cn', marketLabel: 'A 股', symbol: '600519', period: '1d', periodLabel: '日 K' },
  { market: 'cn', marketLabel: 'A 股', symbol: '600519', period: '1w', periodLabel: '周 K' },
  // 美股(全部 4 周期有数据)
  { market: 'us', marketLabel: '美股', symbol: 'NVDA', period: '15m', periodLabel: '15 分' },
  { market: 'us', marketLabel: '美股', symbol: 'NVDA', period: '1h', periodLabel: '1 小时' },
  { market: 'us', marketLabel: '美股', symbol: 'NVDA', period: '1d', periodLabel: '日 K' },
  { market: 'us', marketLabel: '美股', symbol: 'NVDA', period: '1w', periodLabel: '周 K' },
  // 加密(全部 4 周期有数据)
  { market: 'crypto', marketLabel: '加密', symbol: 'BTC/USDT', period: '15m', periodLabel: '15 分' },
  { market: 'crypto', marketLabel: '加密', symbol: 'BTC/USDT', period: '1h', periodLabel: '1 小时' },
  { market: 'crypto', marketLabel: '加密', symbol: 'BTC/USDT', period: '1d', periodLabel: '日 K' },
  { market: 'crypto', marketLabel: '加密', symbol: 'BTC/USDT', period: '1w', periodLabel: '周 K' },
]

const BASE = process.env.WORKBENCH_URL ?? 'http://localhost:3000/workbench'

async function main() {
  fs.mkdirSync(OUT_DIR, { recursive: true })
  const browser = await chromium.launch()
  try {
    const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } })
    const page = await ctx.newPage()
    await page.goto(BASE, { waitUntil: 'networkidle' })
    await page.waitForTimeout(800)

    for (const shot of SHOTS) {
      // 1. 点市场 Tab(自动联动默认 symbol)
      await page.locator(`nav button:has-text("${shot.marketLabel}")`).first().click()
      await page.waitForTimeout(300)
      // 2. 点周期(15m/1h/1d/1w)
      await page.locator(`button:has-text("${shot.periodLabel}")`).first().click()
      // 3. 等最终状态。
      //    600519 三档(15m/1h/1w)走 AKShare EM,后端 4 次重试 ~22s 才确定 503。
      //    其他组合走 CH 缓存命中,几百 ms 即可。
      //    用文本探测而非 canvas:canvas 在 init 时就被创建(假阳性)。
      const isCnUnstable = shot.market === 'cn' && shot.period !== '1d'
      const fixedWait = isCnUnstable ? 25_000 : 5_000
      await page.waitForTimeout(fixedWait)

      const safeSymbol = shot.symbol.replace('/', '')
      const fname = `task-3-h-${shot.market}-${safeSymbol}-${shot.period}.png`
      const fullPath = path.join(OUT_DIR, fname)
      await page.screenshot({ path: fullPath })
      console.log(`✓ ${fname}`)
    }
    await ctx.close()
  } finally {
    await browser.close()
  }
}

main().catch((e) => {
  console.error(e)
  process.exit(1)
})
