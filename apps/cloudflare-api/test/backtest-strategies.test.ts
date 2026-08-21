import { describe, expect, it } from 'vitest'

import { runBacktest } from '../src/backtest'
import type { Kline } from '../src/market'

const items: Kline[] = Array.from({ length: 160 }, (_, index) => {
  const close = 100 + Math.sin(index / 6) * 12
  return {
    ts: new Date(Date.UTC(2026, 0, index + 1)).toISOString(),
    open: close,
    high: close + 2,
    low: close - 2,
    close,
    volume: 1_000,
    amount: null,
  }
})

describe('multi-strategy backtest', () => {
  it('executes both crossover and reversal strategies', () => {
    for (const strategy of ['sma_cross', 'rsi_reversal']) {
      const output = runBacktest(items, {
        symbol: 'BTCUSDT', strategy, initialCash: 10_000, fast: 5, slow: 20,
        leverage: 1, commissionRate: 0, slippageBps: 0,
      })
      expect(output.equity).toHaveLength(items.length)
      expect(output.trades.length).toBeGreaterThan(0)
    }
  })
})
