import { describe, it, expect } from 'vitest'

import { classifyCandle, clampHigh, clampLow, candleGeometry } from './kline.calc'

describe('D3 K线构成口径', () => {
  it('分类:收>开→阳、收<开→阴、收≈开→十字星', () => {
    expect(classifyCandle(100, 105)).toBe('yang')
    expect(classifyCandle(105, 100)).toBe('yin')
    expect(classifyCandle(100, 100)).toBe('doji')
    expect(classifyCandle(100, 100.2)).toBe('doji') // epsilon 内
  })

  it('实体顶/底 = max/min(开,收)(阳阴均成立)', () => {
    const g1 = candleGeometry({ open: 100, high: 130, low: 90, close: 120 })
    expect(g1.bodyTop).toBe(120)
    expect(g1.bodyBottom).toBe(100)
    const g2 = candleGeometry({ open: 120, high: 130, low: 90, close: 100 })
    expect(g2.bodyTop).toBe(120)
    expect(g2.bodyBottom).toBe(100)
  })

  it('约束:最高永不低于实体顶、最低永不高于实体底', () => {
    expect(clampHigh(110, 100, 120)).toBe(120)
    expect(clampHigh(130, 100, 120)).toBe(130)
    expect(clampLow(105, 100, 120)).toBe(100)
    expect(clampLow(90, 100, 120)).toBe(90)
  })

  it('影线非负(即便传入非法高/低)', () => {
    const g = candleGeometry({ open: 100, high: 110, low: 105, close: 120 })
    expect(g.upperShadow).toBeGreaterThanOrEqual(0)
    expect(g.lowerShadow).toBeGreaterThanOrEqual(0)
  })

  it('影线长度正确', () => {
    const g = candleGeometry({ open: 100, high: 130, low: 85, close: 120 })
    expect(g.upperShadow).toBe(10) // 130 - 120
    expect(g.lowerShadow).toBe(15) // 100 - 85
  })
})
