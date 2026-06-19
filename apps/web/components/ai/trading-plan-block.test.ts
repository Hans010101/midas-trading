import { describe, expect, it } from 'vitest'

import { orderDirection } from './trading-plan-block'

// ★ 红线:挂单方向映射 —— crypto 多空都能挂(open_long/open_short);
//   现货(cn/us/hk)只能限价买入,看空不挂(现货不能做空);中性永不挂。
describe('orderDirection · 计划方向 → 挂单方向', () => {
  it('crypto:long→open_long · short→open_short', () => {
    expect(orderDirection('crypto', 'long')).toBe('open_long')
    expect(orderDirection('crypto', 'short')).toBe('open_short')
  })

  it('现货 cn/us/hk:long→buy', () => {
    expect(orderDirection('cn', 'long')).toBe('buy')
    expect(orderDirection('us', 'long')).toBe('buy')
    expect(orderDirection('hk', 'long')).toBe('buy')
  })

  it('★现货看空不挂单(不能做空)→ null', () => {
    expect(orderDirection('cn', 'short')).toBeNull()
    expect(orderDirection('us', 'short')).toBeNull()
    expect(orderDirection('hk', 'short')).toBeNull()
  })

  it('中性任何市场都不挂 → null', () => {
    expect(orderDirection('crypto', 'neutral')).toBeNull()
    expect(orderDirection('cn', 'neutral')).toBeNull()
  })
})
