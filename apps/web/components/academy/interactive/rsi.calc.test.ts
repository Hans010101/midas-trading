import { describe, it, expect } from 'vitest'

import { computeRsi, isOverbought, isOversold, isBlunted } from './rsi.calc'

describe('D12 RSI 口径（含钝化）', () => {
  it('★全涨 → RSI = 100', () => {
    const closes = Array.from({ length: 20 }, (_, i) => i + 1) // 1..20 严格涨
    expect(computeRsi(closes, 14)[14]).toBeCloseTo(100)
  })

  it('★全跌 → RSI = 0', () => {
    const closes = Array.from({ length: 20 }, (_, i) => 20 - i) // 20..1 严格跌
    expect(computeRsi(closes, 14)[14]).toBeCloseTo(0)
  })

  it('★RSI = 100 − 100/(1+RS)（已知 RS 验证）', () => {
    // n=2, closes=[10,12,11]: index2 变化 +2,−1 → gain=2,loss=1,RS=2 → RSI=100−100/3≈66.67
    expect(computeRsi([10, 12, 11], 2)[2]!).toBeCloseTo(66.666, 2)
  })

  it('超买/超卖阈值为参考（70/30）', () => {
    expect(isOverbought(72)).toBe(true)
    expect(isOverbought(68)).toBe(false)
    expect(isOversold(28)).toBe(true)
    expect(isOversold(32)).toBe(false)
  })

  it('★钝化：强趋势中 RSI 连续多根贴超买区不翻转', () => {
    const closes = Array.from({ length: 30 }, (_, i) => i + 1) // 持续强涨
    const rsi = computeRsi(closes, 14)
    expect(isBlunted(rsi, 70, 3, 'overbought')).toBe(true)
  })

  it('震荡行情不构成钝化', () => {
    const closes = [10, 11, 10, 11, 10, 11, 10, 11, 10, 11, 10, 11, 10, 11, 10, 11, 10, 11]
    const rsi = computeRsi(closes, 14)
    expect(isBlunted(rsi, 70, 3, 'overbought')).toBe(false)
  })
})
