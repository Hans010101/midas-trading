/** 沙盘助手可视化纯逻辑单测(第一期)。 */

import { describe, expect, it } from 'vitest'

import { isDivergentFinding, ratioToLongShortPct } from './structure-viz'

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
