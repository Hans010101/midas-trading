import { describe, expect, it } from 'vitest'

import { FUNC_PAGES, MARKET_ORDER, symbolHref } from './command-palette-nav'

describe('symbolHref · 品种 → 统一详情页路由', () => {
  it('策展品种走语义路径', () => {
    expect(symbolHref({ symbol: 'BTCUSDT', market: 'crypto', name: '比特币' })).toBe(
      '/crypto/BTCUSDT',
    )
    expect(symbolHref({ symbol: '600519', market: 'cn', name: '贵州茅台' })).toBe(
      '/cn/600519',
    )
    expect(symbolHref({ symbol: 'NVDA', market: 'us', name: 'NVIDIA' })).toBe('/us/NVDA')
    expect(symbolHref({ symbol: '00700', market: 'hk', name: '腾讯控股' })).toBe('/hk/00700')
  })

  it('长尾品种保留查询参数兜底并正确编码', () => {
    expect(symbolHref({ symbol: 'HUSDT', market: 'crypto' })).toBe(
      '/crypto-preview?symbol=HUSDT',
    )
    expect(symbolHref({ symbol: '688999', market: 'cn', name: '长尾示例' })).toBe(
      `/cn-preview?symbol=688999&name=${encodeURIComponent('长尾示例')}`,
    )
    expect(symbolHref({ symbol: 'BTC/USDT', market: 'crypto' })).toBe(
      `/crypto-preview?symbol=${encodeURIComponent('BTC/USDT')}`,
    )
  })
})

describe('MARKET_ORDER · ★含 hk(原 workbench dialog 漏了)', () => {
  it('四市场都在', () => {
    expect([...MARKET_ORDER].sort()).toEqual(['cn', 'crypto', 'hk', 'us'])
  })
  it('hk 在次序里(港股结果才会显示)', () => {
    expect(MARKET_ORDER).toContain('hk')
  })
})

describe('FUNC_PAGES · 功能页(★不含训练营)', () => {
  it('含 终端/策略研究室/个人中心/自选,路由正确', () => {
    const map = Object.fromEntries(FUNC_PAGES.map((p) => [p.label, p.href]))
    expect(map['终端']).toBe('/workbench')
    expect(map['策略研究室']).toBe('/lab/assistant')
    expect(map['个人中心']).toBe('/account/membership')
    expect(map['会员']).toBeUndefined()
    expect(map['自选']).toBe('/watchlist')
  })

  it('★不含训练营(系统性学习不适合快速跳)', () => {
    expect(FUNC_PAGES.some((p) => p.label.includes('训练营'))).toBe(false)
    expect(FUNC_PAGES.some((p) => p.href.includes('/academy'))).toBe(false)
  })

  it('每个功能页都是静态路由(非 [id] 动态段)', () => {
    for (const p of FUNC_PAGES) {
      expect(p.href).toMatch(/^\/[a-z/-]+$/)
      expect(p.href).not.toContain('[')
    }
  })
})
