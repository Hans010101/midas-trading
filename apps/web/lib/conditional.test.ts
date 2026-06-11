/**
 * 条件单纯逻辑单测 · 触发矩阵与后端 should_trigger 同口径(全含等号)。
 */

import { describe, expect, it } from 'vitest'

import { deviationPct, kindLabel, wouldTriggerNow } from './conditional'

describe('wouldTriggerNow(与后端触发矩阵同口径)', () => {
  const T = 100

  it('LIMIT BUY:P ≤ T 触发(低吸 · 含等号)', () => {
    expect(wouldTriggerNow('limit', 'buy', 'long', T, 99)).toBe(true)
    expect(wouldTriggerNow('limit', 'buy', 'long', T, 100)).toBe(true)
    expect(wouldTriggerNow('limit', 'buy', 'long', T, 101)).toBe(false)
  })

  it('LIMIT SELL:P ≥ T 触发(高抛)', () => {
    expect(wouldTriggerNow('limit', 'sell', 'long', T, 101)).toBe(true)
    expect(wouldTriggerNow('limit', 'sell', 'long', T, 99)).toBe(false)
  })

  it('STOP_LOSS 平多 P ≤ T · 平空 P ≥ T', () => {
    expect(wouldTriggerNow('stop_loss', 'sell', 'long', T, 99)).toBe(true)
    expect(wouldTriggerNow('stop_loss', 'sell', 'long', T, 101)).toBe(false)
    expect(wouldTriggerNow('stop_loss', 'buy', 'short', T, 101)).toBe(true)
    expect(wouldTriggerNow('stop_loss', 'buy', 'short', T, 99)).toBe(false)
  })

  it('TAKE_PROFIT 平多 P ≥ T · 平空 P ≤ T', () => {
    expect(wouldTriggerNow('take_profit', 'sell', 'long', T, 101)).toBe(true)
    expect(wouldTriggerNow('take_profit', 'sell', 'long', T, 99)).toBe(false)
    expect(wouldTriggerNow('take_profit', 'buy', 'short', T, 99)).toBe(true)
    expect(wouldTriggerNow('take_profit', 'buy', 'short', T, 101)).toBe(false)
  })
})

describe('deviationPct', () => {
  it('计算触发价相对现价偏离(绝对值百分比)', () => {
    expect(deviationPct(150, 100)).toBe(50)
    expect(deviationPct(50, 100)).toBe(50)
    expect(deviationPct(100, 100)).toBe(0)
  })

  it('现价缺失 / 非法 → null', () => {
    expect(deviationPct(100, null)).toBeNull()
    expect(deviationPct(100, 0)).toBeNull()
    expect(deviationPct(Number.NaN, 100)).toBeNull()
  })
})

describe('kindLabel', () => {
  it('LIMIT 按 side 细分 · SL/TP 固定', () => {
    expect(kindLabel('limit', 'buy')).toBe('限价买入')
    expect(kindLabel('limit', 'sell')).toBe('限价卖出')
    expect(kindLabel('stop_loss', 'sell')).toBe('止损')
    expect(kindLabel('take_profit', 'buy')).toBe('止盈')
  })
})
