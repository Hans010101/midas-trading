import { describe, it, expect } from 'vitest'

import { sma, stddev, bollingerBands, bandwidth } from './bollinger.calc'

describe('D11 布林带口径（上下轨对称 K=2）', () => {
  it('SMA(N) 正确，不足 N 根为 null', () => {
    expect(sma([2, 4, 6], 3)).toEqual([null, null, 4])
  })

  it('总体标准差（分母 N）', () => {
    const sd = stddev([10, 14], 2)
    expect(sd[1]).toBeCloseTo(2) // sqrt(((10-12)^2+(14-12)^2)/2)=2
  })

  it('★上下轨 = 中轨 ± K×σ，严格对称', () => {
    const b = bollingerBands([10, 14], 2, 2)[1]
    expect(b.mid).toBeCloseTo(12)
    expect(b.upper).toBeCloseTo(16) // 12 + 2*2
    expect(b.lower).toBeCloseTo(8) // 12 - 2*2
    expect(b.upper! - b.mid!).toBeCloseTo(b.mid! - b.lower!) // 对称
  })

  it('K 默认 2', () => {
    const def = bollingerBands([10, 14], 2)
    const k2 = bollingerBands([10, 14], 2, 2)
    expect(def[1].upper).toBeCloseTo(k2[1].upper!)
  })

  it('带宽随波动放大：高波动 > 低波动', () => {
    const calm = bollingerBands([100, 101, 100, 101], 4, 2)
    const wild = bollingerBands([100, 120, 90, 110], 4, 2)
    expect(bandwidth(wild[3])!).toBeGreaterThan(bandwidth(calm[3])!)
  })
})
