import { describe, it, expect } from 'vitest'

import { riskRewardRatio, expectancy, breakEvenWinRate } from './risk-reward.calc'

describe('D18 盈亏比口径', () => {
  it('盈亏比=止盈距离/止损距离', () => {
    expect(riskRewardRatio(200, 100)).toBeCloseTo(2)
  })
  it('★期望=胜率×盈亏比−败率(高盈亏比容忍低胜率)', () => {
    expect(expectancy(0.5, 2)).toBeCloseTo(0.5)
    expect(expectancy(0.4, 2)).toBeCloseTo(0.2) // 40%胜率+2盈亏比仍正期望
    expect(expectancy(0.3, 1)).toBeCloseTo(-0.4) // 低盈亏比+低胜率负期望
  })
  it('★保本胜率=1/(1+盈亏比)(盈亏比越高、保本胜率越低)', () => {
    expect(breakEvenWinRate(2)).toBeCloseTo(1 / 3)
    expect(breakEvenWinRate(1)).toBeCloseTo(0.5)
  })
})
