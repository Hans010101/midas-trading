/** 训练营「去实战练」入口 · href 拼接 + 配置完整性。 */

import { describe, expect, it } from 'vitest'

import { ACADEMY_PRACTICE, buildPracticeHref, getPractice } from './practice'

describe('buildPracticeHref 路由拼接', () => {
  it('四市场策展品种走语义详情路径', () => {
    expect(buildPracticeHref({ market: 'crypto', symbol: 'BTCUSDT', label: '' })).toBe(
      '/crypto/BTCUSDT',
    )
    expect(buildPracticeHref({ market: 'cn', symbol: '600519', label: '' })).toBe(
      '/cn/600519',
    )
    expect(buildPracticeHref({ market: 'us', symbol: 'NVDA', label: '' })).toBe(
      '/us/NVDA',
    )
    expect(buildPracticeHref({ market: 'hk', symbol: '00700', label: '' })).toBe(
      '/hk/00700',
    )
  })

  it('workbench → 裸 /workbench(无 symbol;即便误传也不拼)', () => {
    expect(buildPracticeHref({ market: 'workbench', label: '' })).toBe('/workbench')
    expect(buildPracticeHref({ market: 'workbench', symbol: 'BTCUSDT', label: '' })).toBe(
      '/workbench',
    )
  })

  it('市场缺 symbol → 裸路由', () => {
    expect(buildPracticeHref({ market: 'crypto', label: '' })).toBe('/crypto-preview')
  })

  it('symbol 做 URL 编码', () => {
    expect(buildPracticeHref({ market: 'crypto', symbol: 'BTC/USDT', label: '' })).toBe(
      '/crypto-preview?symbol=BTC%2FUSDT',
    )
  })
})

describe('ACADEMY_PRACTICE 配置完整性', () => {
  it('getPractice 无配置返回 null', () => {
    expect(getPractice('不存在的slug')).toBeNull()
  })

  it.each(Object.entries(ACADEMY_PRACTICE))('「%s」配置合法且 href 不含 [id] 段', (_slug, entry) => {
    expect(entry.label.trim().length).toBeGreaterThan(0)
    expect(['crypto', 'cn', 'us', 'hk', 'workbench']).toContain(entry.market)
    if (entry.market !== 'workbench') {
      expect((entry.symbol ?? '').trim().length).toBeGreaterThan(0)
    }
    const href = buildPracticeHref(entry)
    expect(href.startsWith('/')).toBe(true)
    expect(href).not.toContain('[')
  })
})
