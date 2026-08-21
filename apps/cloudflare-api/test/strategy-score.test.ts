import { describe, expect, it } from 'vitest'

import type { Kline } from '../src/market'
import { scoreStrategy } from '../src/strategy-score'

const params = {
  threshold: 3,
  weights: { boll: 1, macd: 1, ma: 1, rsi: 1, kdj: 1, extreme: 1 },
  atr_stop_mult: 2,
  atr_tp_mult: 4,
}

describe('strategy score', () => {
  it('uses all configured factors and returns ATR risk distance', () => {
    const items: Kline[] = Array.from({ length: 80 }, (_, index) => {
      const close = 100 + index
      return { ts: `${index}`, open: close - 1, high: close + 2, low: close - 2, close, volume: 1, amount: null }
    })
    const output = scoreStrategy(items, params, 3)
    expect(Object.keys(output.contributions)).toHaveLength(6)
    expect(output.score).not.toBe(0)
    expect(output.atr).toBeGreaterThan(0)
  })
})
