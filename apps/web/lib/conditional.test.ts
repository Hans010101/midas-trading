/**
 * 条件单纯逻辑单测 · 触发矩阵与后端 should_trigger 同口径(全含等号)。
 */

import { describe, expect, it } from 'vitest'

import {
  type ConditionalKind,
  PERP_LIMIT_MAX_LEVERAGE,
  deviationPct,
  kindLabel,
  presetDirection,
  presetTriggerPrice,
  validatePerpLimit,
  wouldTriggerNow,
} from './conditional'
import type { OrderSide, PositionSide } from '@/lib/api/virtual'

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

describe('validatePerpLimit(perp 限价表单校验 · 与后端端点同口径)', () => {
  const ok = { triggerPrice: 100000, leverage: 10, margin: 500, marginMode: 'isolated' }

  it('全合法 → null(可提交)', () => {
    expect(validatePerpLimit(ok)).toBeNull()
    expect(validatePerpLimit({ ...ok, marginMode: 'cross' })).toBeNull()
  })

  it('触发价缺失 / ≤0 → 报错', () => {
    expect(validatePerpLimit({ ...ok, triggerPrice: 0 })).toContain('触发价')
    expect(validatePerpLimit({ ...ok, triggerPrice: -1 })).toContain('触发价')
  })

  it('杠杆超范围 / 非整数 → 报错(1-125 · 后端 schema 口径)', () => {
    expect(validatePerpLimit({ ...ok, leverage: 0 })).toContain('杠杆')
    expect(validatePerpLimit({ ...ok, leverage: PERP_LIMIT_MAX_LEVERAGE + 1 })).toContain('杠杆')
    expect(validatePerpLimit({ ...ok, leverage: 200 })).toContain('杠杆')
    expect(validatePerpLimit({ ...ok, leverage: 1.5 })).toContain('杠杆')
    expect(validatePerpLimit({ ...ok, leverage: PERP_LIMIT_MAX_LEVERAGE })).toBeNull() // 125 边界含
    expect(validatePerpLimit({ ...ok, leverage: 1 })).toBeNull()
  })

  it('保证金缺失 / ≤0 → 报错', () => {
    expect(validatePerpLimit({ ...ok, margin: 0 })).toContain('保证金')
    expect(validatePerpLimit({ ...ok, margin: -100 })).toContain('保证金')
  })

  it('保证金模式非法 → 报错', () => {
    expect(validatePerpLimit({ ...ok, marginMode: '' })).toContain('保证金模式')
    expect(validatePerpLimit({ ...ok, marginMode: 'weird' })).toContain('保证金模式')
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

describe('presetDirection / presetTriggerPrice(快捷档位)', () => {
  // 全部合法组合(side = 平仓方向 / limit 的买卖方向,与后端端点口径一致)
  const COMBOS: [ConditionalKind, OrderSide, PositionSide][] = [
    ['stop_loss', 'sell', 'long'],
    ['stop_loss', 'buy', 'short'],
    ['take_profit', 'sell', 'long'],
    ['take_profit', 'buy', 'short'],
    ['limit', 'buy', 'long'],
    ['limit', 'sell', 'long'],
  ]

  it('方向矩阵:SL 平多下/平空上 · TP 平多上/平空下 · LIMIT buy下/sell上', () => {
    expect(presetDirection('stop_loss', 'sell', 'long')).toBe(-1)
    expect(presetDirection('stop_loss', 'buy', 'short')).toBe(1)
    expect(presetDirection('take_profit', 'sell', 'long')).toBe(1)
    expect(presetDirection('take_profit', 'buy', 'short')).toBe(-1)
    expect(presetDirection('limit', 'buy', 'long')).toBe(-1)
    expect(presetDirection('limit', 'sell', 'long')).toBe(1)
  })

  it('★ 全组合 × 全档位:档位价绝不立即触发(与 wouldTriggerNow 互证)', () => {
    for (const [kind, side, pside] of COMBOS) {
      for (const pct of [0.02, 0.05, 0.1]) {
        const price = Number(presetTriggerPrice(kind, side, pside, 100, pct))
        expect(wouldTriggerNow(kind, side, pside, price, 100)).toBe(false)
      }
    }
  })

  it('算价:止损平多 −5% = 95 · 止盈平空 −2% = 98 · 限价卖出 +10% = 110', () => {
    expect(presetTriggerPrice('stop_loss', 'sell', 'long', 100, 0.05)).toBe('95')
    expect(presetTriggerPrice('take_profit', 'buy', 'short', 100, 0.02)).toBe('98')
    expect(presetTriggerPrice('limit', 'sell', 'long', 100, 0.1)).toBe('110')
  })

  it('精度:小币按现价位数展开不截断成 0 · 整数价干净', () => {
    // 0.0895 × 0.95 = 0.085025(完整保留,绝不为 0)
    expect(presetTriggerPrice('stop_loss', 'sell', 'long', 0.0895, 0.05)).toBe('0.085025')
    // 96000 × 0.95 = 91200(无多余尾零)
    expect(presetTriggerPrice('stop_loss', 'sell', 'long', 96000, 0.05)).toBe('91200')
    // 232.45 × 1.02 = 237.099(现价 2 位 → 237.1)
    expect(presetTriggerPrice('take_profit', 'sell', 'long', 232.45, 0.02)).toBe('237.1')
    expect(Number(presetTriggerPrice('stop_loss', 'sell', 'long', 0.0895, 0.05))).toBeGreaterThan(0)
  })
})
