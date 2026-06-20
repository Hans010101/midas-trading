import { describe, it, expect } from 'vitest'

import {
  theoreticalLiqPrice,
  actualLiqPrice,
  equityRatio,
  stepStatus,
} from './liquidation-process.calc'

describe('D8 爆仓全过程口径(维持保证金致实际强平更早)', () => {
  it('理论爆仓价 = entry × (1 − 1/杠杆)(保证金归零)', () => {
    expect(theoreticalLiqPrice(10, 100)).toBeCloseTo(90)
  })

  it('★实际爆仓价比理论【更早】(多单价位更高)', () => {
    // lev=10, entry=100, 维持率0.5%:理论90、实际 100×(1−0.1+0.005)=90.5
    const theo = theoreticalLiqPrice(10, 100)
    const actual = actualLiqPrice(10, 0.005, 100)
    expect(actual).toBeCloseTo(90.5)
    expect(actual).toBeGreaterThan(theo) // 更高价位 = 下跌途中更早触发
  })

  it('权益比随价格下跌单调减少(每步吃掉一格)', () => {
    expect(equityRatio(100, 10, 100)).toBeCloseTo(1) // 开仓价:满仓权益
    const steps = [100, 98, 96, 94, 92].map((p) => equityRatio(p, 10, 100))
    for (let i = 1; i < steps.length; i++) {
      expect(steps[i]).toBeLessThan(steps[i - 1]) // 严格递减
    }
  })

  it('★实际爆仓前每一步都还活着(正权益、可主动止损)', () => {
    // 实际爆仓价 90.5;91 仍在其上 → 未爆仓(仍是止损机会)
    expect(stepStatus(91, 10, 0.005, 100)).not.toBe('liquidated')
    expect(equityRatio(91, 10, 100)).toBeGreaterThan(0)
  })

  it('到达/跌破实际爆仓价 → 判强平', () => {
    expect(stepStatus(90.5, 10, 0.005, 100)).toBe('liquidated')
    expect(stepStatus(90, 10, 0.005, 100)).toBe('liquidated') // 理论价时早已强平
  })
})
