import { describe, it, expect } from 'vitest'

import {
  isolatedLiqPrice,
  crossLiqPrice,
  isolatedMaxLoss,
  crossMaxLoss,
} from './margin-mode.calc'

describe('D6 保证金模式口径(逐仓隔离 / 全仓共担)', () => {
  it('逐仓爆仓价 = entry × (1 ∓ 1/杠杆)(与 D1 同)', () => {
    expect(isolatedLiqPrice('long', 10, 100)).toBeCloseTo(90)
    expect(isolatedLiqPrice('short', 10, 100)).toBeCloseTo(110)
  })

  it('★全仓爆仓价比逐仓【更远】(多单更低、缓冲更大)', () => {
    // positionMargin=100, lev=10 → notional=1000;accountEquity=300(账户里还有别的钱)
    const iso = isolatedLiqPrice('long', 10, 100) // 90
    const cross = crossLiqPrice('long', 10, 100, 100, 300) // 100×(1−300/1000)=70
    expect(cross).toBeCloseTo(70)
    expect(cross).toBeLessThan(iso) // 全仓更靠外(多单更低)
    expect(iso).toBeLessThan(100) // 都在开仓价下方
  })

  it('全仓空单同样更远(更高)', () => {
    const iso = isolatedLiqPrice('short', 10, 100) // 110
    const cross = crossLiqPrice('short', 10, 100, 100, 300) // 100×(1+0.3)=130
    expect(cross).toBeCloseTo(130)
    expect(cross).toBeGreaterThan(iso)
  })

  it('★最大亏损:逐仓限于该仓保证金、全仓是整个账户', () => {
    expect(isolatedMaxLoss(100)).toBe(100) // 封顶于该仓
    expect(crossMaxLoss(300)).toBe(300) // 整个账户
    expect(crossMaxLoss(300)).toBeGreaterThan(isolatedMaxLoss(100)) // 全仓损失面更大
  })

  it('全仓缓冲足够大时多单爆仓价不低于 0', () => {
    // accountEquity ≥ notional → 价格归零也不爆,clamp 到 0
    expect(crossLiqPrice('long', 10, 100, 100, 1200)).toBe(0)
  })
})
