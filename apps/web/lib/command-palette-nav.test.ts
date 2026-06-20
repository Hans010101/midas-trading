import { describe, expect, it } from 'vitest'

import { FUNC_PAGES, MARKET_ORDER, symbolHref } from './command-palette-nav'

describe('symbolHref · 品种 → 详情页路由(零 [id] · ?symbol=)', () => {
  it('crypto → /crypto-preview?symbol=（不带 name）', () => {
    expect(symbolHref({ symbol: 'BTCUSDT', market: 'crypto', name: '比特币' })).toBe(
      '/crypto-preview?symbol=BTCUSDT',
    )
  })

  it('cn → /cn-preview?symbol=&name=（带中文名 · URL 编码）', () => {
    expect(symbolHref({ symbol: '600519', market: 'cn', name: '贵州茅台' })).toBe(
      `/cn-preview?symbol=600519&name=${encodeURIComponent('贵州茅台')}`,
    )
  })

  it('us → /us-preview?symbol=&name=', () => {
    expect(symbolHref({ symbol: 'NVDA', market: 'us', name: 'NVIDIA' })).toBe(
      '/us-preview?symbol=NVDA&name=NVIDIA',
    )
  })

  it('hk → /hk-preview?symbol=&name=（★港股也跳对）', () => {
    expect(symbolHref({ symbol: '00700', market: 'hk', name: '腾讯控股' })).toBe(
      `/hk-preview?symbol=00700&name=${encodeURIComponent('腾讯控股')}`,
    )
  })

  it('无 name 时省略 &name=（cn/us/hk）', () => {
    expect(symbolHref({ symbol: '600519', market: 'cn' })).toBe('/cn-preview?symbol=600519')
    expect(symbolHref({ symbol: '00700', market: 'hk' })).toBe('/hk-preview?symbol=00700')
  })

  it('symbol 含特殊字符也 URL 编码(crypto spot 带斜杠)', () => {
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
  it('含 终端/策略研究室/会员/自选,路由正确', () => {
    const map = Object.fromEntries(FUNC_PAGES.map((p) => [p.label, p.href]))
    expect(map['终端']).toBe('/workbench')
    expect(map['策略研究室']).toBe('/lab/assistant')
    expect(map['会员']).toBe('/account/membership')
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
