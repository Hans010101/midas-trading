/** 顶部市场导航高亮判定单测(修复刀:/account 误亮)· 行为表钉死。 */

import { describe, expect, it } from 'vitest'

import { resolveActiveMarket } from './market-nav'

describe('resolveActiveMarket', () => {
  it('市场首页/详情页 → 对应市场亮(store 无关)', () => {
    expect(resolveActiveMarket('/cn-market', 'crypto')).toBe('cn')
    expect(resolveActiveMarket('/us-market', 'crypto')).toBe('us')
    expect(resolveActiveMarket('/crypto-market', 'cn')).toBe('crypto')
    expect(resolveActiveMarket('/hk-market', 'crypto')).toBe('hk')
    expect(resolveActiveMarket('/crypto-preview?symbol=HUSDT', 'cn')).toBe('crypto')
    expect(resolveActiveMarket('/us-preview', 'crypto')).toBe('us')
  })

  it('workbench → store 兜底(页内切换不变 URL 的唯一合法场景)', () => {
    expect(resolveActiveMarket('/workbench', 'cn')).toBe('cn')
    expect(resolveActiveMarket('/workbench', 'crypto')).toBe('crypto')
  })

  it('★ /account 域(用户中心)→ 全不亮(本次 bug)', () => {
    expect(resolveActiveMarket('/account', 'crypto')).toBeNull()
    expect(resolveActiveMarket('/account/positions', 'crypto')).toBeNull()
    expect(resolveActiveMarket('/account/alerts', 'crypto')).toBeNull()
    expect(resolveActiveMarket('/account/profile', 'crypto')).toBeNull()
  })

  it('其他中性页/未知路径 → 全不亮(白名单天然覆盖未来新页)', () => {
    expect(resolveActiveMarket('/global', 'crypto')).toBeNull()
    expect(resolveActiveMarket('/watchlist', 'crypto')).toBeNull()
    expect(resolveActiveMarket('/lab/assistant', 'crypto')).toBeNull()
    expect(resolveActiveMarket('/whatever-new-page', 'crypto')).toBeNull()
    expect(resolveActiveMarket(null, 'crypto')).toBeNull()
  })
})
