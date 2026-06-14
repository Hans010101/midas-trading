/**
 * 图谱组件渲染单测(移动刀D)· 堵「几何纯函数 → 组件」接缝:
 * lib 单测证了坐标不重叠,这里证组件真把 12 个因子标签全渲染进 SVG
 * (Hans 真机截图的"标签缺失"观感 = 重叠互盖,验收口径 = 12 节点全部有名称标签)。
 */

import { renderToString } from 'react-dom/server'
import { describe, expect, it } from 'vitest'

import type { StructureFactor, StructureSnapshot } from '@/lib/api/structure'
import { FACTOR_LABEL, FACTOR_ORDER, GRAPH_GEOM } from '@/lib/structure-graph'

import { StructureGraph } from './structure-graph'

function factor(value: Record<string, number>): StructureFactor {
  return { value, window: '24h', asof: '2026-06-12T00:00:00Z', text: null }
}

/** 12 因子全非空快照(最坏角密度 = Hans 截图场景)。 */
function fullSnap(): StructureSnapshot {
  return {
    symbol: 'BTCUSDT',
    generated_at: '2026-06-12T00:00:00Z',
    account_long_short: factor({ latest: 1.64, avg_24h: 1.6 }),
    position_long_short: factor({ latest: 1.2, avg_24h: 1.1 }),
    taker_flow: factor({ latest: 0.9, avg_24h: 1.0 }),
    open_interest: factor({ oi_usd: 1e9, oi_coin: 1e4, change_pct_24h: 5.2 }),
    funding_rate: factor({ latest: -0.000013, avg_7d: 0.0001, max_7d: 0.001, min_7d: -0.001 }),
    basis: factor({ mark_price: 99, index_price: 100, basis: -1, basis_pct: -0.95 }),
    sentiment: factor({ fear_greed: 75 }),
    funding_predicted: factor({ latest: 0.000125 }),
    funding_zscore: factor({ z: 2.41, mean_60d: 0.0001, std_60d: 0.0002 }),
    oi_volume_ratio: factor({ ratio: 0.85, oi_usd: 1e9, quote_volume_24h: 1.17e9 }),
    global_long_short: factor({ latest: 1.6, avg_24h: 1.58 }),
    depth: factor({ spread_pct: 0.0005, imbalance: 1.2 }),
  }
}

describe('StructureGraph 组件渲染(12 节点最坏密度)', () => {
  it('★ 12 个因子名称标签全部渲染进 SVG(一个不缺)· viewBox 用 GRAPH_GEOM', () => {
    const html = renderToString(<StructureGraph snapshot={fullSnap()} findings={[]} />)
    for (const key of FACTOR_ORDER) {
      expect(html, `缺标签:${FACTOR_LABEL[key]}`).toContain(FACTOR_LABEL[key])
    }
    expect(html).toContain(`viewBox="0 0 ${GRAPH_GEOM.W} ${GRAPH_GEOM.H}"`)
  })

  it('无 finding → 节点数值行随 headline 中性灰(刀D-B 同源收敛)', () => {
    const html = renderToString(<StructureGraph snapshot={fullSnap()} findings={[]} />)
    // 比值节点数值 1.64 渲染在,且不再带旧版 bull 朱红(无 LLM 判定一律 #9A938A)
    expect(html).toContain('1.64')
    expect(html).not.toContain('fill="#DC143C">1.64')
  })
})
