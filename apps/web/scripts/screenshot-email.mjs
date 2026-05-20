import { chromium } from 'playwright'
import path from 'node:path'

const OUT = '/Users/hans.pan/点金Midas/docs/screenshots'

// 调后端 service 拿邮件 HTML(走 Python 直接渲染)
import { execSync } from 'node:child_process'
const html = execSync(
  `docker compose -f /Users/hans.pan/点金Midas/docker/docker-compose.yaml exec -T api python -c "from app.services.email import _verification_email_html; print(_verification_email_html('https://midas.example/verify-email?token=DEMO'))"`,
  { encoding: 'utf8' },
)

const browser = await chromium.launch()
const ctx = await browser.newContext({ viewport: { width: 760, height: 900 } })
const page = await ctx.newPage()
await page.setContent(html)
await page.waitForTimeout(1000) // 给 web font 一帧
await page.screenshot({ path: path.join(OUT, 'task-3.5-n-email-template.png'), fullPage: true })
console.log('✓ email template captured')
await ctx.close()
await browser.close()
