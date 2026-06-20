import { describe, it, expect } from 'vitest'

import { computeKdj, isOverbought, isOversold, detectKdjCrosses, type KdjPoint } from './kdj.calc'

const ramp = (n: number, step: number, base = 100) => Array.from({ length: n }, (_, i) => base + i * step)

describe('D13 KDJ 口径', () => {
  it('★J = 3K − 2D(逐点成立)', () => {
    const closes = ramp(30, 1.2)
    const highs = closes.map((c) => c + 1)
    const lows = closes.map((c) => c - 1)
    for (const p of computeKdj(highs, lows, closes)) {
      expect(p.j).toBeCloseTo(3 * p.k - 2 * p.d)
    }
  })

  it('★J 可超出 0~100(强涨末端 J > 100)', () => {
    const closes = ramp(30, 3)
    const highs = closes.map((c) => c + 0.5)
    const lows = closes.map((c) => c - 0.5)
    const pts = computeKdj(highs, lows, closes)
    expect(Math.max(...pts.map((p) => p.j))).toBeGreaterThan(100)
  })

  it('★J 可低于 0(强跌末端 J < 0)', () => {
    const closes = ramp(30, -3, 200)
    const highs = closes.map((c) => c + 0.5)
    const lows = closes.map((c) => c - 0.5)
    const pts = computeKdj(highs, lows, closes)
    expect(Math.min(...pts.map((p) => p.j))).toBeLessThan(0)
  })

  it('★KDJ 金叉 = K 上穿 D;死叉 = K 下穿 D', () => {
    const golden: KdjPoint[] = [
      { k: 40, d: 50, j: 20 },
      { k: 60, d: 50, j: 80 },
    ]
    expect(detectKdjCrosses(golden)).toEqual([{ index: 1, type: 'golden' }])
    const death: KdjPoint[] = [
      { k: 60, d: 50, j: 80 },
      { k: 40, d: 50, j: 20 },
    ]
    expect(detectKdjCrosses(death)).toEqual([{ index: 1, type: 'death' }])
  })

  it('超买/超卖为参考(K/D > 80 / < 20)', () => {
    expect(isOverbought({ k: 85, d: 82, j: 90 })).toBe(true)
    expect(isOverbought({ k: 85, d: 70, j: 90 })).toBe(false) // 需 K、D 同时
    expect(isOversold({ k: 15, d: 18, j: 5 })).toBe(true)
    expect(isOversold({ k: 25, d: 18, j: 5 })).toBe(false)
  })
})
