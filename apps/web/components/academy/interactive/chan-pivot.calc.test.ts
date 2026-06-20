import { describe, it, expect } from 'vitest'

import { computePivot } from './chan-pivot.calc'

describe('D2 缠论中枢口径(ZG=min高 / ZD=max低)', () => {
  it('ZG 取三段高点最小值,且【绝不】取最大值(反测)', () => {
    const highs = [110, 108, 112]
    const { zg } = computePivot(highs, [95, 92, 98])
    expect(zg).toBe(108)
    expect(zg).toBe(Math.min(...highs))
    expect(zg).not.toBe(Math.max(...highs)) // 显式钉死:不是 max
  })

  it('ZD 取三段低点最大值,且【绝不】取最小值(反测)', () => {
    const lows = [95, 92, 98]
    const { zd } = computePivot([110, 108, 112], lows)
    expect(zd).toBe(98)
    expect(zd).toBe(Math.max(...lows))
    expect(zd).not.toBe(Math.min(...lows)) // 显式钉死:不是 min
  })

  it('三段有共同重叠 → 构成中枢(ZD<ZG)', () => {
    const r = computePivot([125, 120, 128], [95, 100, 98])
    expect(r.zg).toBe(120)
    expect(r.zd).toBe(100)
    expect(r.formed).toBe(true)
  })

  it('阶梯式无共同重叠 → 不构成中枢(ZD>ZG)', () => {
    const r = computePivot([100, 90, 80], [92, 82, 72])
    expect(r.zg).toBe(80)
    expect(r.zd).toBe(92)
    expect(r.formed).toBe(false)
  })

  it('边界 ZD==ZG(相切不重叠)→ 不构成(严格 <)', () => {
    const r = computePivot([100, 100, 100], [100, 100, 100])
    expect(r.formed).toBe(false)
  })
})
