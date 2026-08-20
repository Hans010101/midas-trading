import { describe, expect, it } from 'vitest'

import { buildBollDigest, classifyBoll } from '../src/boll-scan'
import type { Kline } from '../src/market'

describe('Telegram market scan', () => {
  it('classifies one shared snapshot and builds the hourly digest', () => {
    const klines: Kline[] = Array.from({ length: 30 }, (_, index) => ({
      ts: new Date(index * 900_000).toISOString(),
      open: 100 + index * 0.2,
      high: 100.2 + index * 0.2,
      low: 99.8 + index * 0.2,
      close: 100 + index * 0.2,
      volume: 1_000,
      amount: null,
    }))
    const item = classifyBoll(klines)

    expect(item).toMatchObject({ state: 'trend_up', bias: '偏多' })
    expect(buildBollDigest(
      [{ ...item!, symbol: 'BTCUSDT', change_pct_24h: 2.4 }],
      '12:00',
    )).toContain('BTCUSDT｜三线齐上·上升结构')
  })
})
