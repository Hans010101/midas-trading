import { describe, it, expect } from 'vitest'

import { maxLoss, notionalForRisk, marginUsed, computeSizing } from './position-sizing.calc'

describe('D5 仓位反推口径(杠杆不决定单笔亏损)', () => {
  it('单笔最大亏损 = 权益 × 风险%', () => {
    expect(maxLoss(10000, 0.01)).toBeCloseTo(100)
    expect(maxLoss(10000, 0.02)).toBeCloseTo(200)
  })

  it('应开名义仓位 = 最大亏损 / 止损%', () => {
    expect(notionalForRisk(10000, 0.01, 0.05)).toBeCloseTo(2000) // 100 / 5%
    expect(notionalForRisk(10000, 0.01, 0.1)).toBeCloseTo(1000) // 止损越宽,仓位越小
  })

  it('★核心:换杠杆,最大亏损与名义仓位【纹丝不动】,只有保证金变', () => {
    const a = computeSizing(10000, 0.01, 0.05, 5)
    const b = computeSizing(10000, 0.01, 0.05, 50)
    expect(b.maxLoss).toBe(a.maxLoss) // 杠杆无关
    expect(b.notional).toBe(a.notional) // 杠杆无关
    expect(b.marginUsed).not.toBe(a.marginUsed) // 只有保证金随杠杆变
    expect(a.marginUsed).toBeCloseTo(400) // 2000 / 5
    expect(b.marginUsed).toBeCloseTo(40) // 2000 / 50
  })

  it('占用保证金 = 名义 / 杠杆', () => {
    expect(marginUsed(2000, 10)).toBeCloseTo(200)
  })

  it('止损要在爆仓之前:止损% < 爆仓距(1/杠杆)才安全', () => {
    expect(computeSizing(10000, 0.01, 0.05, 10).stopSafe).toBe(true) // 止损5% < 爆仓距10%
    expect(computeSizing(10000, 0.01, 0.05, 25).stopSafe).toBe(false) // 止损5% > 爆仓距4% → 危险
  })
})
