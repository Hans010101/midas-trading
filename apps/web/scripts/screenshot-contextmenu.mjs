/**
 * Task 5 补 · 右键 K 线 ContextMenu 截图。
 *
 * 用 hans@test.com 测试账号 · 默认在加密 Tab(BTC/USDT)。
 * 输出:
 *   - task-5-context-menu-active.png · 已激活账户 · 买卖项可用
 *   - task-5-context-menu-disabled.png · 未激活账户 · 买卖项 disabled
 */

import { chromium } from 'playwright'
import path from 'node:path'
import fs from 'node:fs'
import { execSync } from 'node:child_process'
import { fileURLToPath } from 'node:url'

const __filename = fileURLToPath(import.meta.url)
const __dirname = path.dirname(__filename)
const OUT_DIR = path.resolve(__dirname, '..', '..', '..', 'docs', 'screenshots')

const EMAIL = 'hans@test.com'
const PASSWORD = 'Test123456'

function sql(query) {
  const cmd = `cd /Users/hans.pan/点金Midas && docker compose -f docker/docker-compose.yaml exec -T postgres psql -U midas -d midas -tA -c "${query.replace(/"/g, '\\"')}"`
  return execSync(cmd, { encoding: 'utf8' }).trim()
}

async function main() {
  fs.mkdirSync(OUT_DIR, { recursive: true })

  // 拿 user_id 用于切换激活/未激活
  const userId = sql(`SELECT id FROM "user" WHERE email='${EMAIL}'`)
  console.log('  user_id:', userId)

  // 状态 1:激活加密账户(确保有金额)
  sql(`INSERT INTO virtual_account (user_id, market, currency, initial_capital, cash_balance, realized_pnl, activated_at, updated_at) VALUES ('${userId}', 'crypto', 'USDT', 100000, 100000, 0, now(), now()) ON CONFLICT (user_id, market) DO UPDATE SET cash_balance = 100000, realized_pnl = 0`)

  const browser = await chromium.launch()
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } })
  const page = await ctx.newPage()

  // 登录
  await page.goto('http://localhost:3000/login', { waitUntil: 'networkidle' })
  await page.locator('input[type="email"]').fill(EMAIL)
  await page.locator('input[type="password"]').fill(PASSWORD)
  await page.locator('button:has-text("登录")').click()
  await page.waitForURL('**/workbench', { timeout: 10_000 })
  await page.waitForTimeout(2500)

  // 切到加密 Tab(已激活)
  await page.locator('nav[aria-label="市场切换"] button:has-text("加密")').click()
  await page.waitForTimeout(1500)

  // 右键 K 线 trigger(KlineContextMenu 包裹的 div)
  const chartTrigger = page.locator('div.flex-1.overflow-hidden.rounded-lg.border.border-paper').first()
  await chartTrigger.click({ button: 'right', position: { x: 300, y: 200 } })
  // 等 radix menu render(portal · role=menu)
  await page.locator('[role="menu"]').first().waitFor({ state: 'visible', timeout: 5000 })
  await page.waitForTimeout(300)
  await page.screenshot({ path: path.join(OUT_DIR, 'task-5-context-menu-active.png') })
  console.log('  ✓ 截图 1: 已激活 · 买卖可用')
  await page.keyboard.press('Escape')
  await page.waitForTimeout(400)

  // 状态 2:切到美股(未激活) + 右键 → disabled
  await page.locator('nav[aria-label="市场切换"] button:has-text("美股")').click()
  await page.waitForTimeout(1500)
  // 先 DELETE 美股账户确保 disabled
  sql(`DELETE FROM virtual_account WHERE user_id='${userId}' AND market='us'`)
  await page.reload({ waitUntil: 'networkidle' })
  await page.waitForTimeout(2500)
  await page.locator('nav[aria-label="市场切换"] button:has-text("美股")').click()
  await page.waitForTimeout(1500)

  const chartTrigger2 = page.locator('div.flex-1.overflow-hidden.rounded-lg.border.border-paper').first()
  await chartTrigger2.click({ button: 'right', position: { x: 300, y: 200 } })
  await page.locator('[role="menu"]').first().waitFor({ state: 'visible', timeout: 5000 })
  await page.waitForTimeout(300)
  await page.screenshot({ path: path.join(OUT_DIR, 'task-5-context-menu-disabled.png') })
  console.log('  ✓ 截图 2: 美股未激活 · 买卖 disabled + 提示')

  await ctx.close()
  await browser.close()
  console.log('\n✓ 2 张截图已保存到', OUT_DIR)
}

main().catch((e) => {
  console.error('FAIL:', e)
  process.exit(1)
})
