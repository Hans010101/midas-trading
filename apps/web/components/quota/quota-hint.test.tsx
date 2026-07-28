/** QuotaHint 三态渲染单测(会员刀2)· 登录墙页面无法 preview,renderToString 钉死。 */

import { renderToString } from 'react-dom/server'
import { describe, expect, it } from 'vitest'

import { QuotaHint } from './quota-hint'

describe('QuotaHint 三态', () => {
  it('null(加载/未登录)→ 不渲染', () => {
    expect(renderToString(<QuotaHint item={null} />)).toBe('')
  })

  it('有余量 → 「今日剩 N/20 次」灰字 · 无会员链接', () => {
    const html = renderToString(<QuotaHint item={{ feature: 'diagnose', limit: 20, used: 3 }} />)
    expect(html).toContain('今日剩 17/20 次')
    expect(html).not.toContain('membership')
  })

  it('耗尽 → 仅说明自动恢复，不出现商业升级入口', () => {
    const html = renderToString(<QuotaHint item={{ feature: 'diagnose', limit: 20, used: 20 }} />)
    expect(html).toContain('今日额度已用完')
    expect(html).toContain('明日自动恢复')
    expect(html).not.toContain('membership')
    expect(html).not.toContain('进阶版')
  })
})
