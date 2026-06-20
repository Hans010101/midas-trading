import { describe, it, expect } from 'vitest'

import { notionalExposure, pnl, computePnl } from './pnl-exposure.calc'

describe('D7 盈亏与敞口口径(盈亏按名义敞口算)', () => {
  it('名义敞口 = 保证金 × 杠杆', () => {
    expect(notionalExposure(1000, 10)).toBeCloseTo(10000)
  })

  it('★盈亏按名义敞口算,【不是】按保证金算(破误区)', () => {
    // 保证金1000、10x、反向5%:盈亏 = 10000×(−5%) = −500,绝不是 1000×(−5%) = −50
    expect(pnl(1000, 10, -0.05)).toBeCloseTo(-500)
    expect(pnl(1000, 10, -0.05)).not.toBeCloseTo(-50) // 显式钉死:不是按保证金
  })

  it('盈亏占保证金比 = 杠杆 × 价格变动%', () => {
    expect(computePnl(1000, 10, -0.05).pnlPctOfMargin).toBeCloseTo(-0.5) // 亏掉一半保证金
    expect(computePnl(1000, 20, 0.03).pnlPctOfMargin).toBeCloseTo(0.6)
  })

  it('★"只投1000最多亏1000"是错的:10x 下反向10%就亏光爆仓', () => {
    const r = computePnl(1000, 10, -0.1) // 10000×(−10%) = −1000 = 全部保证金
    expect(r.pnl).toBeCloseTo(-1000)
    expect(r.liquidated).toBe(true) // 仅10%反向即爆仓
  })

  it('高杠杆更小反向即爆仓:20x 下 −5% 即亏光', () => {
    expect(computePnl(1000, 20, -0.05).liquidated).toBe(true) // 20×5% = 100%
    expect(computePnl(1000, 5, -0.05).liquidated).toBe(false) // 5×5% = 25%,未爆
  })
})
