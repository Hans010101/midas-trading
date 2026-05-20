import { chromium } from 'playwright'
import path from 'node:path'

const OUT = '/Users/hans.pan/点金Midas/docs/screenshots'
const browser = await chromium.launch()
const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } })
const page = await ctx.newPage()

// 1) /workbench 未登录 → 跳 /login
await page.goto('http://localhost:3000/workbench', { waitUntil: 'networkidle' })
await page.waitForTimeout(500)
console.log('  current URL after /workbench (unauth):', page.url())
await page.screenshot({ path: path.join(OUT, 'task-3.5-n-redirect-to-login.png') })

// 2) /register 页
await page.goto('http://localhost:3000/register', { waitUntil: 'networkidle' })
await page.waitForTimeout(500)
await page.screenshot({ path: path.join(OUT, 'task-3.5-n-register.png') })

// 3) /login 页
await page.goto('http://localhost:3000/login', { waitUntil: 'networkidle' })
await page.waitForTimeout(500)
await page.screenshot({ path: path.join(OUT, 'task-3.5-n-login.png') })

// 4) /verify-email (用刚才注册的 token,如果还在 logs 中)
// 不重新注册,用通用错误态(已使用 token)展示
await page.goto('http://localhost:3000/verify-email?token=invalid-token-demo', { waitUntil: 'networkidle' })
await page.waitForTimeout(1500)
await page.screenshot({ path: path.join(OUT, 'task-3.5-n-verify-email-error.png') })

await ctx.close()
await browser.close()
console.log('✓ 4 screenshots saved')
