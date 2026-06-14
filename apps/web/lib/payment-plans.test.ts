/**
 * 会员档位/定价纯函数单测(Phase 2a 刀2)· 价格如实 + 折算正确。
 */

import { describe, expect, it } from 'vitest'

import {
  monthlyEquivalent,
  PLAN_TIERS,
  savingsPct,
} from './payment-plans'

describe('PLAN_TIERS 价格如实(与后端 PRICE_USDT 同口径)', () => {
  it('月/季/年 = 4.9 / 9.9 / 19.9 USDT', () => {
    const byPeriod = Object.fromEntries(PLAN_TIERS.map((t) => [t.period, t.priceUsdt]))
    expect(byPeriod).toEqual({ month: '4.9', quarter: '9.9', year: '19.9' })
  })

  it('年度高亮(最划算)· 月度无折扣标记', () => {
    expect(PLAN_TIERS.find((t) => t.period === 'year')?.highlight).toBe(true)
    expect(PLAN_TIERS.find((t) => t.period === 'month')?.highlight).toBeUndefined()
  })
})

describe('monthlyEquivalent 月均折算', () => {
  it('月 4.9 → 4.90 · 季 9.9/3 → 3.30 · 年 19.9/12 → 1.66', () => {
    expect(monthlyEquivalent({ priceUsdt: '4.9', months: 1 })).toBe('4.90')
    expect(monthlyEquivalent({ priceUsdt: '9.9', months: 3 })).toBe('3.30')
    expect(monthlyEquivalent({ priceUsdt: '19.9', months: 12 })).toBe('1.66')
  })
})

describe('savingsPct 相对按月省', () => {
  it('月度=0 · 季度≈33% · 年度≈66%', () => {
    expect(savingsPct({ priceUsdt: '4.9', months: 1 })).toBe(0)
    // 9.9 / (4.9×3=14.7) = 0.673 → 省 33%
    expect(savingsPct({ priceUsdt: '9.9', months: 3 })).toBe(33)
    // 19.9 / (4.9×12=58.8) = 0.338 → 省 66%
    expect(savingsPct({ priceUsdt: '19.9', months: 12 })).toBe(66)
  })
})
