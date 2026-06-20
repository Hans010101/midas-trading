import { describe, it, expect } from 'vitest'

import { ema, computeMacd, detectMacdCrosses, type MacdPoint } from './macd.calc'

describe('D10 MACD 口径（金叉=DIF上穿DEA，与均线区分）', () => {
  it('EMA 递推：α = 2/(n+1)', () => {
    const e = ema([1, 2, 3, 4], 3) // α=0.5
    expect(e[0]).toBeCloseTo(1)
    expect(e[1]).toBeCloseTo(1.5)
    expect(e[2]).toBeCloseTo(2.25)
    expect(e[3]).toBeCloseTo(3.125)
  })

  it('常数价格 → DIF/DEA/柱 全 0', () => {
    const pts = computeMacd(new Array(30).fill(100))
    expect(pts[29].dif).toBeCloseTo(0)
    expect(pts[29].dea).toBeCloseTo(0)
    expect(pts[29].hist).toBeCloseTo(0)
  })

  it('★MACD 柱 = (DIF − DEA) × 2（逐点成立）', () => {
    const closes = [10, 11, 12, 11, 10, 9, 10, 12, 14, 13, 12, 11, 13, 15, 16, 15, 14, 16, 18, 17]
    const pts = computeMacd(closes)
    for (const p of pts) {
      expect(p.hist).toBeCloseTo((p.dif - p.dea) * 2)
    }
  })

  it('★MACD 金叉 = DIF 上穿 DEA；死叉 = DIF 下穿 DEA', () => {
    const golden: MacdPoint[] = [
      { dif: -1, dea: 0, hist: -2 },
      { dif: 1, dea: 0, hist: 2 },
    ]
    expect(detectMacdCrosses(golden)).toEqual([{ index: 1, type: 'golden' }])
    const death: MacdPoint[] = [
      { dif: 1, dea: 0, hist: 2 },
      { dif: -1, dea: 0, hist: -2 },
    ]
    expect(detectMacdCrosses(death)).toEqual([{ index: 1, type: 'death' }])
  })

  it('★与 D9 区分：判定对象是 DIF/DEA 两条派生线（只看 DIF−DEA 符号），不接触价格或价格均线', () => {
    // detectMacdCrosses 仅接受 MacdPoint(dif/dea/hist)，类型上即排除价格均线输入
    const pts: MacdPoint[] = [
      { dif: 0, dea: 1, hist: -2 },
      { dif: 2, dea: 1, hist: 2 },
    ]
    // i=1: d0=0−1=−1≤0, d1=2−1=1>0 → golden
    expect(detectMacdCrosses(pts)).toEqual([{ index: 1, type: 'golden' }])
  })
})
