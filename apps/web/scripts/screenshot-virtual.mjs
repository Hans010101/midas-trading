/**
 * Task 5 · Checkpoint R · 虚拟交易 6 张截图 + 端到端验收链路。
 *
 * 前置:
 *   1. docker compose 全栈 healthy
 *   2. 测试用户 hans-virtual@midas.example(脚本启动时如不存在会自动注册 + verify)
 *   3. 默认全新状态(无激活账户)用于截图 1-2
 *
 * 输出:
 *   - task-5-r-settings-empty.png   设置页 · 三市场全未激活
 *   - task-5-r-workbench-disabled.png 工作台 · 买入按钮 disabled + 未设置提示
 *   - task-5-r-confirm-buy.png      下单确认模态(买入 NVDA)
 *   - task-5-r-toast-filled.png     成交 toast(帝王金)
 *   - task-5-r-portfolio-single.png /portfolio · 仅 1 个市场卡 + 1 条曲线
 *   - task-5-r-position-card.png    右栏当前标的持仓摘要
 *
 * 用法:
 *   node apps/web/scripts/screenshot-virtual.mjs
 */

import { chromium } from 'playwright'
import path from 'node:path'
import fs from 'node:fs'
import { execSync } from 'node:child_process'
import { fileURLToPath } from 'node:url'

const __filename = fileURLToPath(import.meta.url)
const __dirname = path.dirname(__filename)
const OUT_DIR = path.resolve(__dirname, '..', '..', '..', 'docs', 'screenshots')

const EMAIL = 'hans-virtual@midas.example'
const PASSWORD = 'virtualpass1234'

function sql(query) {
  const cmd = `cd /Users/hans.pan/点金Midas && docker compose -f docker/docker-compose.yaml exec -T postgres psql -U midas -d midas -tA -c "${query.replace(/"/g, '\\"')}"`
  return execSync(cmd, { encoding: 'utf8' }).trim()
}

async function ensureUser() {
  // 注册(409 if 存在,忽略)
  const reg = await fetch('http://localhost:8000/api/v1/auth/register', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email: EMAIL, password: PASSWORD, age_confirmed: true }),
  })
  if (reg.status === 201 || reg.status === 409) {
    // success or already-exists
  } else {
    throw new Error(`Register failed: ${reg.status}`)
  }
  // verify(如未 verify · 拿 token 调 /verify)
  const userId = sql(`SELECT id FROM "user" WHERE email='${EMAIL}'`)
  const token = sql(
    `SELECT token FROM verification_token WHERE user_id='${userId}' AND consumed_at IS NULL ORDER BY created_at DESC LIMIT 1`,
  )
  if (token) {
    await fetch('http://localhost:8000/api/v1/auth/verify', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ token }),
    })
  }

  // 重置状态:清空所有 virtual_account(级联清 position/order/snapshot)
  sql(`DELETE FROM virtual_account WHERE user_id='${userId}'`)
}

async function main() {
  fs.mkdirSync(OUT_DIR, { recursive: true })

  console.log('▶ ensure test user + reset 虚拟账户状态')
  await ensureUser()

  const browser = await chromium.launch()
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } })
  const page = await ctx.newPage()

  // === 登录 ===
  await page.goto('http://localhost:3000/login', { waitUntil: 'networkidle' })
  await page.locator('input[type="email"]').fill(EMAIL)
  await page.locator('input[type="password"]').fill(PASSWORD)
  await page.locator('button:has-text("登录")').click()
  await page.waitForURL('**/workbench', { timeout: 10_000 })
  await page.waitForTimeout(2500)

  // === 截图 2: workbench 未激活 disabled 按钮 ===
  await page.screenshot({ path: path.join(OUT_DIR, 'task-5-r-workbench-disabled.png') })
  console.log('  ✓ 截图 1: workbench disabled')

  // === 截图 1: /settings/wallet 三市场全未激活 ===
  await page.goto('http://localhost:3000/settings/wallet', { waitUntil: 'networkidle' })
  await page.waitForTimeout(1000)
  await page.screenshot({ path: path.join(OUT_DIR, 'task-5-r-settings-empty.png') })
  console.log('  ✓ 截图 2: settings empty')

  // === 激活 美股 100,000(NVDA 数据可用)· 找第 2 个输入框(0=cn,1=us,2=crypto)===
  const inputs = page.locator('input[type="number"]')
  await inputs.nth(1).fill('100000')
  // 同一卡片内的「激活并保存」按钮(默认是 2nd · 但按钮文案在每卡都一致,只点 us 卡的)
  // 用 has-text 配合 :nth-of-type 取美股那张卡里的按钮
  const buttons = page.locator('button:has-text("激活并保存")')
  await buttons.nth(1).click() // 0=cn,1=us,2=crypto
  await page.waitForTimeout(1500)

  // === 回 workbench ===
  await page.goto('http://localhost:3000/workbench', { waitUntil: 'networkidle' })
  await page.waitForTimeout(2000)
  // 切到美股(header 的市场 Tab,不是 watchlist 里的 NVDA 行)
  await page.locator('nav[aria-label="市场切换"] button:has-text("美股")').click()
  await page.waitForTimeout(800)

  // === 点买入 → 截图 3: confirm 模态 ===
  await page.locator('header button:has-text("买入")').click()
  await page.waitForTimeout(1200) // 等市价拉到 + 估算算出
  await page.screenshot({ path: path.join(OUT_DIR, 'task-5-r-confirm-buy.png') })
  console.log('  ✓ 截图 3: confirm modal')

  // === 确认买入 → 截图 4: toast ===
  await page.locator('div[role="dialog"] button:has-text("确认买入")').click()
  await page.waitForTimeout(800)
  await page.screenshot({ path: path.join(OUT_DIR, 'task-5-r-toast-filled.png') })
  console.log('  ✓ 截图 4: toast filled')
  await page.waitForTimeout(2200) // 等 toast 自动消失

  // === 截图 6: 右栏持仓摘要(刚买完应该有持仓)===
  await page.waitForTimeout(1500)
  await page.screenshot({ path: path.join(OUT_DIR, 'task-5-r-position-card.png') })
  console.log('  ✓ 截图 5: right column position card')

  // === 截图 5: /portfolio 单市场 ===
  await page.goto('http://localhost:3000/portfolio', { waitUntil: 'networkidle' })
  await page.waitForTimeout(2500)
  await page.screenshot({ path: path.join(OUT_DIR, 'task-5-r-portfolio-single.png') })
  console.log('  ✓ 截图 6: portfolio single market')

  await ctx.close()
  await browser.close()
  console.log('\n✓ 6 张截图已保存到', OUT_DIR)
}

main().catch((e) => {
  console.error('FAIL:', e)
  process.exit(1)
})
