import { describe, expect, it } from 'vitest'

import type { StrategyKind } from '@/lib/api/strategy'
import { availableStrategies, effectiveOrder } from '@/lib/strategy-order'

// 5 个通用信号(四市场都有)
const FIVE: StrategyKind[] = [
  'ma_cross',
  'rsi_reversal',
  'boll_reversion',
  'macd_cross',
  'kdj_cross',
]

describe('availableStrategies · 按市场过滤(★extreme 仅 crypto perp)', () => {
  it('crypto perp → 6 个(含 extreme)', () => {
    const avail = availableStrategies('crypto', 'perp')
    expect(avail).toHaveLength(6)
    expect(avail).toContain('extreme')
  })

  it('crypto spot(现货)→ 5 个(不含 extreme)', () => {
    const avail = availableStrategies('crypto', 'spot')
    expect(avail).toHaveLength(5)
    expect(avail).not.toContain('extreme')
  })

  it('crypto 未指定 instrument → 当现货 5 个(extreme 需明确 perp)', () => {
    const avail = availableStrategies('crypto')
    expect(avail).not.toContain('extreme')
  })

  it.each(['cn', 'us', 'hk'] as const)('%s 现货 → 5 个通用(不含 extreme)', (mkt) => {
    const avail = availableStrategies(mkt, 'spot')
    expect(avail).toHaveLength(5)
    expect(avail).not.toContain('extreme')
    expect(avail).toEqual(FIVE)
  })

  it('★现货即使误传 instrument=perp 也不出 extreme(只 crypto+perp 双条件)', () => {
    expect(availableStrategies('cn', 'perp')).not.toContain('extreme')
    expect(availableStrategies('us', 'perp')).not.toContain('extreme')
  })
})

describe('effectiveOrder · 用户顺序 ∩ 可用集 + 缺失补全', () => {
  it('空 stored → 按可用集默认顺序', () => {
    const avail = availableStrategies('crypto', 'perp')
    expect(effectiveOrder([], avail)).toEqual(avail)
  })

  it('保留用户已存顺序(可用项),缺失的可用项按默认顺序追加在后', () => {
    const avail = availableStrategies('crypto', 'perp')
    const stored: StrategyKind[] = ['kdj_cross', 'ma_cross']
    const order = effectiveOrder(stored, avail)
    expect(order.slice(0, 2)).toEqual(['kdj_cross', 'ma_cross']) // 用户顺序在前
    expect(order).toHaveLength(6)
    expect(order).toContain('extreme') // 缺失的可用项被补全
  })

  it('★现货:stored 里残留的 extreme 被过滤掉(不在可用集)', () => {
    const avail = availableStrategies('cn', 'spot') // 不含 extreme
    const stored: StrategyKind[] = ['extreme', 'rsi_reversal', 'ma_cross']
    const order = effectiveOrder(stored, avail)
    expect(order).not.toContain('extreme') // 关键:现货不显示 extreme
    expect(order).toHaveLength(5)
    expect(order[0]).toBe('rsi_reversal') // extreme 被剔除,其余保序
  })

  it('crypto perp:stored 含 extreme → 保留', () => {
    const avail = availableStrategies('crypto', 'perp')
    const stored: StrategyKind[] = ['extreme', 'ma_cross']
    const order = effectiveOrder(stored, avail)
    expect(order[0]).toBe('extreme')
    expect(order).toHaveLength(6)
  })

  it('未知/陈旧 key 不在可用集 → 被过滤', () => {
    const avail = availableStrategies('crypto', 'perp')
    const stored = ['bogus_old_key', 'ma_cross'] as unknown as StrategyKind[]
    const order = effectiveOrder(stored, avail)
    expect(order).not.toContain('bogus_old_key' as StrategyKind)
    expect(order).toHaveLength(6)
  })
})
