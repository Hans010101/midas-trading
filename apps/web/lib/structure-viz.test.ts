/** 沙盘助手可视化纯逻辑单测(一期 + 二期刀2 数值格式化/语义配置)。 */

import { describe, expect, it } from 'vitest'

import type { StructureFactor, StructureSnapshot } from '@/lib/api/structure'
import {
  CALIBER_NOTE,
  buildFactorCards,
  factorHeadline,
  isDivergentFinding,
  ratioToLongShortPct,
  sparklineSpec,
  stateTone,
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
    // 三期批1 +4
    funding_predicted: factor({ latest: 0.000125 }),
    funding_zscore: factor({ z: 2.41, mean_60d: 0.0001, std_60d: 0.0002 }),
    oi_volume_ratio: factor({ ratio: 0.853, oi_usd: 1e9, quote_volume_24h: 1.17e9 }),
    global_long_short: factor({ latest: 1.6, avg_24h: 1.58 }),
    // 三期批2 +1:盘口深度
    depth: factor({ spread_pct: 0.0005, imbalance: 1.2 }),
    ...over,
  }
}

describe('factorHeadline(全部取 snapshot 结构化字段 · 不解析 LLM 文字)', () => {
  it('数值格式:比值 2 位 · 费率 ×100 4 位% · OI 带符号 · 基差 3 位 · FGI 整数', () => {
    expect(factorHeadline('account_long_short', snap())?.text).toBe('1.64')
    expect(factorHeadline('funding_rate', snap())?.text).toBe('-0.0013%')
    expect(factorHeadline('open_interest', snap())?.text).toBe('+5.23%')
    expect(factorHeadline('basis', snap())?.text).toBe('-0.952%')
    expect(factorHeadline('sentiment', snap())?.text).toBe('75')
  })

  it('缺因子 / 缺字段 → null(优雅降级)', () => {
    expect(factorHeadline('position_long_short', snap())).toBeNull()
    expect(factorHeadline('sentiment', snap({ sentiment: factor({ btc_dominance: 52 }) }))).toBeNull()
    expect(factorHeadline('unknown_factor', snap())).toBeNull()
  })
})

// ── 移动刀D-B · tone 档位收敛:跟 finding.state,不再「数值 vs 固定基准」────────
describe('tone 档位收敛(刀D-B:有判定才有方向色 · 无判定中性灰)', () => {
  it('stateTone 档位映射:含多 bull · 含空 bear · 其余 neutral', () => {
    expect(stateTone('偏多')).toBe('bull')
    expect(stateTone('极端偏多')).toBe('bull')
    expect(stateTone('略偏空')).toBe('bear')
    expect(stateTone('中性')).toBe('neutral')
    expect(stateTone('与价格背离')).toBe('neutral')
  })

  it('★ 无 finding → 一律 neutral(1.64 比值 / 负费率 / FGI 75 都不再自行染色)', () => {
    expect(factorHeadline('account_long_short', snap())?.tone).toBe('neutral')
    expect(factorHeadline('funding_rate', snap())?.tone).toBe('neutral')
    expect(factorHeadline('open_interest', snap())?.tone).toBe('neutral')
    expect(factorHeadline('basis', snap())?.tone).toBe('neutral')
    expect(factorHeadline('sentiment', snap())?.tone).toBe('neutral')
    expect(factorHeadline('funding_predicted', snap())?.tone).toBe('neutral')
    expect(factorHeadline('global_long_short', snap())?.tone).toBe('neutral')
    expect(factorHeadline('oi_volume_ratio', snap())?.tone).toBe('neutral')
  })

  it('★ 有 finding → tone 跟档位:偏多 bull / 偏空 bear / 中性 neutral', () => {
    expect(factorHeadline('account_long_short', snap(), { state: '偏多' })?.tone).toBe('bull')
    expect(factorHeadline('funding_rate', snap(), { state: '偏空' })?.tone).toBe('bear')
    // LLM 判中性 → 即使数值偏离基准(1.64)也灰(与状态胶囊同源不打架)
    expect(factorHeadline('account_long_short', snap(), { state: '中性' })?.tone).toBe('neutral')
  })

  it('★ 特例 funding_zscore:|z|>2 数据极端才按符号着色,不跟 finding 档', () => {
    expect(factorHeadline('funding_zscore', snap())).toEqual({ text: '2.41', tone: 'bull' })
    const mild = snap({ funding_zscore: factor({ z: -1.2, mean_60d: 0, std_60d: 0.0002 }) })
    expect(factorHeadline('funding_zscore', mild)?.tone).toBe('neutral')
    // 区间内即使 LLM 给了偏空档,z 卡仍中性(极端才有语义)
    expect(factorHeadline('funding_zscore', mild, { state: '偏空' })?.tone).toBe('neutral')
  })
})

describe('sparklineSpec(基准线 + 线色与 headline 同源)', () => {
  it('比值类 baseline=1 · 费率/基差 baseline=0 · 无 finding 线色中性灰', () => {
    expect(sparklineSpec('account_long_short', snap())).toEqual({ baseline: 1, stroke: '#9A938A' })
    expect(sparklineSpec('funding_rate', snap())).toEqual({ baseline: 0, stroke: '#9A938A' })
    expect(sparklineSpec('basis', snap())).toEqual({ baseline: 0, stroke: '#9A938A' })
  })

  it('有 finding → 线色跟档位(偏多朱红 / 偏空墨绿)', () => {
    expect(sparklineSpec('account_long_short', snap(), { state: '偏多' }).stroke).toBe('#DC143C')
    expect(sparklineSpec('funding_rate', snap(), { state: '偏空' }).stroke).toBe('#0F6E5F')
  })

  it('OI 无基准线 · 缺因子默认帝王金无基准线(一期行为)', () => {
    expect(sparklineSpec('open_interest', snap())).toEqual({ stroke: '#9A938A' })
    expect(sparklineSpec('taker_flow', snap())).toEqual({ baseline: 1, stroke: '#B8860B' })
  })
})

describe('factorHeadline 三期批1 四分支(数值格式不随刀D-B 变)', () => {
  it('预测费率同 funding 百分比格式 · global 同比值格式(并入 RATIO_FACTORS)', () => {
    expect(factorHeadline('funding_predicted', snap())?.text).toBe('0.0125%')
    expect(factorHeadline('global_long_short', snap())?.text).toBe('1.60')
    expect(sparklineSpec('global_long_short', snap()).baseline).toBe(1)
  })

  it('OI 成交额比两位小数 · 缺因子 null', () => {
    expect(factorHeadline('oi_volume_ratio', snap())?.text).toBe('0.85')
    expect(factorHeadline('oi_volume_ratio', snap({ oi_volume_ratio: null }))).toBeNull()
  })

  it('二批刀3:盘口深度 失衡+价差 · 任一缺只显有效项 · 全缺 null', () => {
    // spread_pct 0.0005 → 价差 0.050% · imbalance 1.2 → 失衡 1.20
    expect(factorHeadline('depth', snap())?.text).toBe('失衡 1.20 · 价差 0.050%')
    // 只有 imbalance(spread 缺)→ 只显失衡
    expect(factorHeadline('depth', snap({ depth: factor({ imbalance: 2.5 }) }))?.text).toBe('失衡 2.50')
    // 全缺 → null(脏数据留白)
    expect(factorHeadline('depth', snap({ depth: factor({}) }))).toBeNull()
    expect(factorHeadline('depth', snap({ depth: null }))).toBeNull()
  })
})

describe('buildFactorCards + CALIBER_NOTE(批1 修复刀)', () => {
  it('snapshot 驱动:有 finding 附判定 · 无 finding 降级(finding=null)· null 因子无卡', () => {
    const findings = [
      { factor: 'account_long_short', state: '偏多', detail: 'x', window: '24h' },
      { factor: 'funding_rate', state: '中性', detail: 'y', window: '7d' },
    ]
    const cards = buildFactorCards(snap(), findings)
    const byKey = new Map(cards.map((c) => [c.key, c]))
    // 有 finding → 附判定
    expect(byKey.get('account_long_short')?.finding?.state).toBe('偏多')
    // snapshot 有值但 LLM 没点名 → 降级卡(finding null · 不伪造)
    expect(byKey.has('funding_zscore')).toBe(true)
    expect(byKey.get('funding_zscore')?.finding).toBeNull()
    expect(byKey.get('funding_zscore')?.window).toBe('24h') // 取 snapshot 因子 window
    // snapshot null(position/taker 基线为 null)→ 无卡
    expect(byKey.has('position_long_short')).toBe(false)
  })

  it('排序照 FACTOR_ORDER(与图谱一致)', () => {
    const keys = buildFactorCards(snap(), []).map((c) => c.key)
    expect(keys).toEqual([
      'account_long_short', 'global_long_short', 'open_interest', 'oi_volume_ratio',
      'funding_rate', 'funding_predicted', 'funding_zscore', 'basis', 'sentiment', 'depth',
    ])
  })

  it('口径文案与 prompts 红线三对齐:不含"全市场人数比/盘口深度" · 清算仍在', () => {
    expect(CALIBER_NOTE).not.toContain('全市场人数比')
    expect(CALIBER_NOTE).toContain('清算数据')
    // ★ 盘口深度二批已采,移出未采集口径(与 prompts 红线三同步)
    expect(CALIBER_NOTE).not.toContain('盘口深度')
  })
})
