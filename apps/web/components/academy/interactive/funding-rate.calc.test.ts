import { describe, it, expect } from 'vitest'

import { fundingPayer, fundingPayment, payerAmount, cumulativeCost } from './funding-rate.calc'

describe('D4 资金费率口径(正费率多头付空头)', () => {
  it('★正费率 → 多头付费(绝不是空头)', () => {
    expect(fundingPayer(0.0001)).toBe('long')
    expect(fundingPayer(0.0001)).not.toBe('short') // 显式钉死方向
    expect(fundingPayer(0.01)).toBe('long')
  })

  it('★负费率 → 空头付费(绝不是多头)', () => {
    expect(fundingPayer(-0.0001)).toBe('short')
    expect(fundingPayer(-0.0001)).not.toBe('long') // 显式钉死方向
  })

  it('零费率 → 无人付费、金额为 0', () => {
    expect(fundingPayer(0)).toBe('none')
    expect(fundingPayment(10000, 0)).toBe(0)
  })

  it('单次结算金额 = 名义 × 费率(带符号,正=多头付出)', () => {
    expect(fundingPayment(10000, 0.0001)).toBeCloseTo(1)
    expect(fundingPayment(10000, -0.0001)).toBeCloseTo(-1)
    expect(payerAmount(10000, -0.0001)).toBeCloseTo(1) // 付费方实付恒非负
  })

  it('累计持有成本 = |名义 × 费率| × 结算次数', () => {
    expect(cumulativeCost(10000, 0.0001, 3)).toBeCloseTo(3)
    expect(cumulativeCost(10000, -0.0002, 5)).toBeCloseTo(10) // 负费率也算正成本(对付费方)
  })
})
