import { describe, it, expect } from 'vitest'

import { liquidationPrice, bufferPct, ENTRY_PRICE } from './liquidation.calc'

describe('D1 爆仓价口径', () => {
  it('多单在开仓价下方、空单在上方(lev>1 恒成立)', () => {
    for (const lev of [2, 5, 10, 25, 50, 100]) {
      const long = liquidationPrice('long', lev)
      const short = liquidationPrice('short', lev)
      expect(long).toBeLessThan(ENTRY_PRICE)
      expect(short).toBeGreaterThan(ENTRY_PRICE)
      expect(long).toBeLessThan(short)
    }
  })

  it('具体值 lev=10 → 多 90 / 空 110', () => {
    expect(liquidationPrice('long', 10)).toBeCloseTo(90)
    expect(liquidationPrice('short', 10)).toBeCloseTo(110)
  })

  it('具体值 lev=4 → 多 75 / 空 125', () => {
    expect(liquidationPrice('long', 4)).toBeCloseTo(75)
    expect(liquidationPrice('short', 4)).toBeCloseTo(125)
  })

  it('杠杆越高,爆仓价越贴近开仓价(单调趋近 100)', () => {
    expect(liquidationPrice('long', 2)).toBeLessThan(liquidationPrice('long', 10))
    expect(liquidationPrice('long', 10)).toBeLessThan(liquidationPrice('long', 50))
    expect(liquidationPrice('short', 2)).toBeGreaterThan(liquidationPrice('short', 10))
    expect(liquidationPrice('short', 10)).toBeGreaterThan(liquidationPrice('short', 50))
  })

  it('容错空间随杠杆收缩:bufferPct = 100/lev', () => {
    expect(bufferPct('long', 10)).toBeCloseTo(10)
    expect(bufferPct('long', 100)).toBeCloseTo(1)
    expect(bufferPct('short', 4)).toBeCloseTo(25)
  })

  it('lev=1 边界:多单理论=0(价格归零才爆)、空单=200', () => {
    expect(liquidationPrice('long', 1)).toBeCloseTo(0)
    expect(liquidationPrice('short', 1)).toBeCloseTo(200)
  })
})
