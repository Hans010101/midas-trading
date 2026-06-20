import { describe, it, expect } from 'vitest'

import { betAtStreak, cumulativeStake, bustStreak } from './martingale.calc'

describe('D21 马丁格尔口径(反面演示:必爆仓)', () => {
  it('★下注额指数膨胀 base×2^n', () => {
    expect(betAtStreak(1, 0)).toBe(1)
    expect(betAtStreak(1, 3)).toBe(8)
    expect(betAtStreak(1, 10)).toBe(1024) // 连亏10次单注已1024倍
  })
  it('★累计投入指数膨胀 base×(2^(n+1)−1)', () => {
    expect(cumulativeStake(1, 3)).toBe(15) // 1+2+4+8
  })
  it('★有限本金必然爆仓(连亏到某次累计超本金)', () => {
    const n = bustStreak(100, 1)
    expect(n).toBeGreaterThan(0)
    expect(Number.isFinite(n)).toBe(true)
    expect(cumulativeStake(1, n)).toBeGreaterThan(100)
  })
})
