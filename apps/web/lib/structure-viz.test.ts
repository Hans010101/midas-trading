/** 沙盘助手可视化纯逻辑单测(一期 + 二期刀2 数值格式化/语义配置)。 */

import { describe, expect, it } from 'vitest'

import type { StructureFactor, StructureSnapshot } from '@/lib/api/structure'
import {
  factorHeadline,
  isDivergentFinding,
  ratioToLongShortPct,
  sparklineSpec,
} from './structure-viz'

describe('isDivergentFinding(背离/极端高亮判定)', () => {
  it('state 含「背离」/「极端」→ 高亮', () => {
    expect(isDivergentFinding({ state: '与价格背离', detail: 'x' })).toBe(true)
    expect(isDivergentFinding({ state: '极端偏多', detail: 'x' })).toBe(true)
  })

  it('detail 含关键词同样命中(LLM 可能写在细节里)', () => {
    expect(isDivergentFinding({ state: '偏多', detail: 'OI 与价格出现背离迹象' })).toBe(true)
  })

  it('普通状态不高亮', () => {
    expect(isDivergentFinding({ state: '中性', detail: '处于近 7 天均值附近' })).toBe(false)
    expect(isDivergentFinding({ state: '偏多', detail: '略高于均值' })).toBe(false)
  })
})

describe('ratioToLongShortPct(比值 → 双边占比)', () => {
  it('ratio 1.65 → 多 62.3% / 空 37.7%(和恒为 100)', () => {
    const r = ratioToLongShortPct(1.65)
    expect(r).not.toBeNull()
    expect(r!.longPct).toBeCloseTo(62.3, 1)
    expect(r!.longPct + r!.shortPct).toBeCloseTo(100, 5)
  })

  it('ratio 1 → 50/50 · ratio 0.5 → 33.3/66.7', () => {
    expect(ratioToLongShortPct(1)!.longPct).toBeCloseTo(50, 1)
    expect(ratioToLongShortPct(0.5)!.longPct).toBeCloseTo(33.3, 1)
  })

  it('非法输入(0 / 负 / NaN)→ null(条不渲染优雅降级)', () => {
    expect(ratioToLongShortPct(0)).toBeNull()
    expect(ratioToLongShortPct(-1)).toBeNull()
    expect(ratioToLongShortPct(Number.NaN)).toBeNull()
  })
})

// ── 二期刀2 · factorHeadline / sparklineSpec ────────────────────────────────

function factor(value: Record<string, number>): StructureFactor {
  return { value, window: '24h', asof: '2026-06-12T00:00:00Z', text: null }
}

function snap(over: Partial<StructureSnapshot> = {}): StructureSnapshot {
  return {
    symbol: 'BTCUSDT',
    generated_at: '2026-06-12T00:00:00Z',
    account_long_short: factor({ latest: 1.6364, avg_24h: 1.6 }),
    position_long_short: null,
    taker_flow: null,
    open_interest: factor({ oi_usd: 1e9, oi_coin: 1e4, change_pct_24h: 5.234 }),
    funding_rate: factor({ latest: -0.000013, avg_7d: 0.0001, max_7d: 0.001, min_7d: -0.001 }),
    basis: factor({ mark_price: 99, index_price: 100, basis: -1, basis_pct: -0.9517 }),
    sentiment: factor({ fear_greed: 75 }),
    ...over,
  }
}

describe('factorHeadline(全部取 snapshot 结构化字段 · 不解析 LLM 文字)', () => {
  it('比值类 2 位小数 + tone:>1 bull / <1 bear', () => {
    expect(factorHeadline('account_long_short', snap())).toEqual({ text: '1.64', tone: 'bull' })
    expect(
      factorHeadline('account_long_short', snap({
        account_long_short: factor({ latest: 0.82, avg_24h: 0.9 }),
      })),
    ).toEqual({ text: '0.82', tone: 'bear' })
  })

  it('费率 ×100 → 4 位小数百分比 + 符号 tone', () => {
    expect(factorHeadline('funding_rate', snap())).toEqual({ text: '-0.0013%', tone: 'bear' })
  })

  it('OI 用 change_pct_24h 带符号 · 基差 3 位小数 · FGI 整数(≥70 bull / ≤30 bear)', () => {
    expect(factorHeadline('open_interest', snap())).toEqual({ text: '+5.23%', tone: 'bull' })
    expect(factorHeadline('basis', snap())).toEqual({ text: '-0.952%', tone: 'bear' })
    expect(factorHeadline('sentiment', snap())).toEqual({ text: '75', tone: 'bull' })
  })

  it('缺因子 / 缺字段 → null(优雅降级)', () => {
    expect(factorHeadline('position_long_short', snap())).toBeNull()
    expect(factorHeadline('sentiment', snap({ sentiment: factor({ btc_dominance: 52 }) }))).toBeNull()
    expect(factorHeadline('unknown_factor', snap())).toBeNull()
  })
})

describe('sparklineSpec(基准线 + 语义线色)', () => {
  it('比值类 baseline=1 · 费率/基差 baseline=0 · 线色随 tone', () => {
    expect(sparklineSpec('account_long_short', snap())).toEqual({ baseline: 1, stroke: '#DC143C' })
    expect(sparklineSpec('funding_rate', snap())).toEqual({ baseline: 0, stroke: '#0F6E5F' })
    expect(sparklineSpec('basis', snap())).toEqual({ baseline: 0, stroke: '#0F6E5F' })
  })

  it('OI 无基准线 · 缺因子默认帝王金无基准线(一期行为)', () => {
    expect(sparklineSpec('open_interest', snap())).toEqual({ stroke: '#DC143C' })
    expect(sparklineSpec('taker_flow', snap())).toEqual({ baseline: 1, stroke: '#B8860B' })
  })
})
