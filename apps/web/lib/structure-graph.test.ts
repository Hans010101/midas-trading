/** 图谱规则引擎单测(二期刀1)· 每条规则:命中 / 不命中 / 缺因子跳过。 */

import { describe, expect, it } from 'vitest'

import type { StructureFactor, StructureSnapshot } from '@/lib/api/structure'
import { deriveGraphEdges } from './structure-graph'

function factor(value: Record<string, number>): StructureFactor {
  return { value, window: '24h', asof: '2026-06-12T00:00:00Z', text: null }
}

/** 全因子中性基线(无任何规则命中)· 各用例按需覆写。 */
function snap(over: Partial<StructureSnapshot> = {}): StructureSnapshot {
  return {
    symbol: 'BTCUSDT',
    generated_at: '2026-06-12T00:00:00Z',
    account_long_short: factor({ latest: 1.0, avg_24h: 1.0 }),
    position_long_short: factor({ latest: 1.0, avg_24h: 1.0 }),
    taker_flow: factor({ latest: 1.0, avg_24h: 1.0 }),
    open_interest: factor({ oi_usd: 1e9, oi_coin: 1e4, change_pct_24h: 0 }),
    funding_rate: factor({ latest: 0, avg_7d: 0, max_7d: 0, min_7d: 0 }),
    basis: factor({ mark_price: 100, index_price: 100, basis: 0, basis_pct: 0 }),
    sentiment: factor({ fear_greed: 50 }),
    ...over,
  }
}

function edgeKeys(s: StructureSnapshot): string[] {
  return deriveGraphEdges(s).map((e) => `${e.from}->${e.to}:${e.type}`)
}

it('全中性基线 → 零边', () => {
  expect(deriveGraphEdges(snap())).toEqual([])
})

describe('R1 账户比↔费率背离', () => {
  it('偏多 + 负费率 → 背离(含中文 reason)', () => {
    const edges = deriveGraphEdges(snap({
      account_long_short: factor({ latest: 1.3, avg_24h: 1.2 }),
      funding_rate: factor({ latest: -0.0002, avg_7d: 0.0001, max_7d: 0.001, min_7d: -0.001 }),
    }))
    const e = edges.find((x) => x.from === 'account_long_short' && x.to === 'funding_rate')
    expect(e?.type).toBe('divergence')
    expect(e?.reason).toContain('背离')
  })

  it('偏空 + 正费率 → 背离(对称)· 同向不命中', () => {
    expect(edgeKeys(snap({
      account_long_short: factor({ latest: 0.8, avg_24h: 0.8 }),
      funding_rate: factor({ latest: 0.0003, avg_7d: 0.0001, max_7d: 0.001, min_7d: 0 }),
    }))).toContain('account_long_short->funding_rate:divergence')
    // 偏多 + 正费率 = 同向 → R1 不出边(但会触发 R7 链?basis=0 不满足 → 无)
    expect(edgeKeys(snap({
      account_long_short: factor({ latest: 1.3, avg_24h: 1.2 }),
      funding_rate: factor({ latest: 0.0003, avg_7d: 0.0001, max_7d: 0.001, min_7d: 0 }),
    }))).toEqual([])
  })

  it('缺 funding 因子 → 整条跳过不报错', () => {
    expect(deriveGraphEdges(snap({
      account_long_short: factor({ latest: 1.3, avg_24h: 1.2 }),
      funding_rate: null,
    }))).toEqual([])
  })
})

describe('R2/R3 账户↔持仓 劈叉/共振', () => {
  it('方向劈叉 → 背离', () => {
    expect(edgeKeys(snap({
      account_long_short: factor({ latest: 1.2, avg_24h: 1.1 }),
      position_long_short: factor({ latest: 0.85, avg_24h: 0.9 }),
    }))).toContain('account_long_short->position_long_short:divergence')
  })

  it('同向且都偏离 >0.15 → 共振(带方向)· 同向但偏离不足不命中', () => {
    const edges = deriveGraphEdges(snap({
      account_long_short: factor({ latest: 1.3, avg_24h: 1.2 }),
      position_long_short: factor({ latest: 1.2, avg_24h: 1.1 }),
    }))
    const e = edges.find((x) => x.to === 'position_long_short')
    expect(e?.type).toBe('resonance')
    expect(e?.direction).toBe('bull')
    // 偏离不足(1.1 / 1.05)→ 不出边
    expect(edgeKeys(snap({
      account_long_short: factor({ latest: 1.1, avg_24h: 1.0 }),
      position_long_short: factor({ latest: 1.05, avg_24h: 1.0 }),
    }))).toEqual([])
  })

  it('缺持仓比 → 跳过', () => {
    expect(deriveGraphEdges(snap({
      account_long_short: factor({ latest: 1.3, avg_24h: 1.2 }),
      position_long_short: null,
    }))).toEqual([])
  })
})

describe('R4/R5 OI↔taker', () => {
  it('增仓 + 卖压 → 背离;增仓 + 买盘 → bull 共振;减仓 + 卖压 → bear 共振', () => {
    expect(edgeKeys(snap({
      open_interest: factor({ oi_usd: 1e9, oi_coin: 1e4, change_pct_24h: 5 }),
      taker_flow: factor({ latest: 0.9, avg_24h: 1.0 }),
    }))).toContain('open_interest->taker_flow:divergence')
    const bull = deriveGraphEdges(snap({
      open_interest: factor({ oi_usd: 1e9, oi_coin: 1e4, change_pct_24h: 5 }),
      taker_flow: factor({ latest: 1.2, avg_24h: 1.0 }),
    })).find((e) => e.from === 'open_interest')
    expect(bull?.type).toBe('resonance')
    expect(bull?.direction).toBe('bull')
    const bear = deriveGraphEdges(snap({
      open_interest: factor({ oi_usd: 1e9, oi_coin: 1e4, change_pct_24h: -5 }),
      taker_flow: factor({ latest: 0.8, avg_24h: 1.0 }),
    })).find((e) => e.from === 'open_interest')
    expect(bear?.direction).toBe('bear')
  })

  it('变化在 ±3% 内不命中 · 缺 OI 跳过', () => {
    expect(edgeKeys(snap({
      open_interest: factor({ oi_usd: 1e9, oi_coin: 1e4, change_pct_24h: 2 }),
      taker_flow: factor({ latest: 0.8, avg_24h: 1.0 }),
    }))).toEqual([])
    expect(deriveGraphEdges(snap({
      open_interest: null,
      taker_flow: factor({ latest: 0.8, avg_24h: 1.0 }),
    }))).toEqual([])
  })
})

describe('R6 基差↔账户比背离 + R7 三角共振链', () => {
  it('贴水 + 偏多 → 背离', () => {
    expect(edgeKeys(snap({
      basis: factor({ mark_price: 99, index_price: 100, basis: -1, basis_pct: -1 }),
      account_long_short: factor({ latest: 1.2, avg_24h: 1.1 }),
    }))).toContain('basis->account_long_short:divergence')
  })

  it('费率正+升水+偏多 → 两条 bull 共振边(链)', () => {
    const edges = deriveGraphEdges(snap({
      funding_rate: factor({ latest: 0.0002, avg_7d: 0.0001, max_7d: 0.001, min_7d: 0 }),
      basis: factor({ mark_price: 101, index_price: 100, basis: 1, basis_pct: 1 }),
      account_long_short: factor({ latest: 1.2, avg_24h: 1.1 }),
    }))
    const chain = edges.filter((e) => e.type === 'resonance' && e.direction === 'bull')
    expect(chain.map((e) => `${e.from}->${e.to}`)).toEqual([
      'funding_rate->basis',
      'basis->account_long_short',
    ])
  })

  it('三者不全同向 → 无链;缺 basis → 跳过', () => {
    expect(edgeKeys(snap({
      funding_rate: factor({ latest: 0.0002, avg_7d: 0.0001, max_7d: 0.001, min_7d: 0 }),
      basis: factor({ mark_price: 99, index_price: 100, basis: -1, basis_pct: -1 }),
      account_long_short: factor({ latest: 1.0, avg_24h: 1.0 }),
    }))).toEqual([])
    expect(deriveGraphEdges(snap({ basis: null }))).toEqual([])
  })
})

describe('R8 情绪↔费率共振', () => {
  it('FGI≥70 且费率高于均值 → bull;FGI≤30 且负费率 → bear', () => {
    const greed = deriveGraphEdges(snap({
      sentiment: factor({ fear_greed: 75 }),
      funding_rate: factor({ latest: 0.0003, avg_7d: 0.0001, max_7d: 0.001, min_7d: 0 }),
    }))
    // 注意:fgi 用例里费率为正且账户中性 → R1/R7 不混入
    expect(greed.map((e) => `${e.from}->${e.to}:${e.direction}`)).toContain(
      'sentiment->funding_rate:bull',
    )
    const fear = deriveGraphEdges(snap({
      sentiment: factor({ fear_greed: 20 }),
      funding_rate: factor({ latest: -0.0002, avg_7d: 0, max_7d: 0, min_7d: -0.001 }),
    }))
    expect(fear.map((e) => `${e.from}->${e.to}:${e.direction}`)).toContain(
      'sentiment->funding_rate:bear',
    )
  })

  it('FGI 中性(50)不命中 · 缺 sentiment 跳过', () => {
    expect(edgeKeys(snap({
      funding_rate: factor({ latest: 0.0003, avg_7d: 0.0001, max_7d: 0.001, min_7d: 0 }),
    }))).toEqual([])
    expect(deriveGraphEdges(snap({
      sentiment: null,
      funding_rate: factor({ latest: -0.0002, avg_7d: 0, max_7d: 0, min_7d: -0.001 }),
    }))).toEqual([])
  })
})
