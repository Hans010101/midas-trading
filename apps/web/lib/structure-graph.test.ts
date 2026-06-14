/** 图谱规则引擎单测(二期刀1)· 每条规则:命中 / 不命中 / 缺因子跳过。 */

import { describe, expect, it } from 'vitest'

import type { StructureFactor, StructureSnapshot } from '@/lib/api/structure'
import { GRAPH_GEOM, deriveGraphEdges, layoutGraphNode } from './structure-graph'

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
    // 三期批1 基线:全 null(R9/R10 不触发 · 缺因子跳过)
    funding_predicted: null,
    funding_zscore: null,
    oi_volume_ratio: null,
    global_long_short: null,
    depth: null,
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

describe('R9 预测费率↔当期费率均值 反号背离(三期批1)', () => {
  it('预估为负 × 7d 均值为正 → 背离;同号不命中', () => {
    expect(edgeKeys(snap({
      funding_predicted: factor({ latest: -0.0002 }),
      funding_rate: factor({ latest: 0.0001, avg_7d: 0.0002, max_7d: 0.001, min_7d: 0 }),
    }))).toContain('funding_predicted->funding_rate:divergence')
    // 同号(都正)→ 不出 R9 边
    expect(edgeKeys(snap({
      funding_predicted: factor({ latest: 0.0001 }),
      funding_rate: factor({ latest: 0.0001, avg_7d: 0.0002, max_7d: 0.001, min_7d: 0 }),
    }))).not.toContain('funding_predicted->funding_rate:divergence')
  })

  it('缺 funding_predicted → 跳过(基线零边)', () => {
    expect(edgeKeys(snap({
      funding_rate: factor({ latest: 0.0001, avg_7d: 0.0002, max_7d: 0.001, min_7d: 0 }),
    }))).toEqual([])
  })
})

describe('R10 费率 z-score 极端 × 结构同向 共振(三期批1)', () => {
  it('z>2 且账户比偏多 → bull;z<-2 且偏空 → bear', () => {
    const bull = deriveGraphEdges(snap({
      funding_zscore: factor({ z: 2.5, mean_60d: 0.0001, std_60d: 0.0002 }),
      account_long_short: factor({ latest: 1.3, avg_24h: 1.2 }),
      // 账户比偏多 + 费率 0 → R1 不触发,隔离 R10
    })).find((e) => e.from === 'funding_zscore')
    expect(bull?.type).toBe('resonance')
    expect(bull?.direction).toBe('bull')

    const bear = deriveGraphEdges(snap({
      funding_zscore: factor({ z: -2.5, mean_60d: 0, std_60d: 0.0002 }),
      account_long_short: factor({ latest: 0.8, avg_24h: 0.85 }),
    })).find((e) => e.from === 'funding_zscore')
    expect(bear?.direction).toBe('bear')
  })

  it('z 极端但结构反向 / z 不极端 / 缺 zscore → 不出 R10 边', () => {
    expect(edgeKeys(snap({
      funding_zscore: factor({ z: 2.5, mean_60d: 0, std_60d: 0.0002 }),
      account_long_short: factor({ latest: 0.9, avg_24h: 0.9 }),
    })).filter((k) => k.startsWith('funding_zscore'))).toEqual([])
    expect(edgeKeys(snap({
      funding_zscore: factor({ z: 1.5, mean_60d: 0, std_60d: 0.0002 }),
      account_long_short: factor({ latest: 1.3, avg_24h: 1.2 }),
    })).filter((k) => k.startsWith('funding_zscore'))).toEqual([])
    expect(edgeKeys(snap({
      account_long_short: factor({ latest: 1.3, avg_24h: 1.2 }),
    })).filter((k) => k.startsWith('funding_zscore'))).toEqual([])
  })
})

describe('图谱标签几何(移动刀D · 数学钉死不重叠/不出界)', () => {
  // 标签包围盒:名称行最长 7 字 ×10px(宽 70)+ 数值行,两行高 ~22px;
  // anchor start=向右展开 / end=向左 / middle=居中。
  function labelBox(i: number, n: number) {
    const p = layoutGraphNode(i, n)
    const W = 70
    const x0 = p.anchor === 'start' ? p.labelX : p.anchor === 'end' ? p.labelX - W : p.labelX - W / 2
    return { x0, x1: x0 + W, y0: p.labelY - 11, y1: p.labelY + 11 }
  }

  it('★ 11 节点任意两标签包围盒互不相交(刀2 布局 9 对重叠 → 0 对)', () => {
    const n = 11
    for (let i = 0; i < n; i++) {
      for (let j = i + 1; j < n; j++) {
        const a = labelBox(i, n)
        const b = labelBox(j, n)
        const overlap = a.x0 < b.x1 && b.x0 < a.x1 && a.y0 < b.y1 && b.y0 < a.y1
        expect(overlap, `节点 ${i} 与 ${j} 标签重叠`).toBe(false)
      }
    }
  })

  it('11 节点全部标签在 viewBox 内(不被裁切 = 不再"缺失")', () => {
    for (let i = 0; i < 11; i++) {
      const b = labelBox(i, 11)
      expect(b.x0).toBeGreaterThanOrEqual(0)
      expect(b.x1).toBeLessThanOrEqual(GRAPH_GEOM.W)
      expect(b.y0).toBeGreaterThanOrEqual(0)
      expect(b.y1).toBeLessThanOrEqual(GRAPH_GEOM.H)
    }
  })

  it('7 节点(老因子数)同样无重叠 · 锚点象限正确', () => {
    for (let i = 0; i < 7; i++) {
      for (let j = i + 1; j < 7; j++) {
        const a = labelBox(i, 7)
        const b = labelBox(j, 7)
        expect(a.x0 < b.x1 && b.x0 < a.x1 && a.y0 < b.y1 && b.y0 < a.y1).toBe(false)
      }
    }
    expect(layoutGraphNode(0, 11).anchor).toBe('middle') // 正上
    const right = layoutGraphNode(3, 11) // ~8° 右侧
    expect(right.anchor).toBe('start')
  })
})
