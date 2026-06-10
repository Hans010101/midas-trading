/**
 * 量纲契约单测(ADR 0040)· 锁死 fmtPct(比率×100) vs fmtPctNum(百分比数值不×100)的差异。
 * ★ 用真机实测值做断言(P1-4e.fix:return_pct=-2.76 曾被 fmtPct 显示成 -276%)· 不用 0 值
 *   (0 在两种量纲下相同,侧证不了契约 —— 审计报告教训)。
 */
import { describe, expect, it } from 'vitest'

import { fmtInt, fmtNum, fmtPct, fmtPctNum, fmtRatio } from './format-backtest'

describe('fmtPct · 比率 ×100(metrics/drawdown 用)', () => {
  it('0.1 比率 → +10.00%', () => {
    expect(fmtPct(0.1)).toBe('+10.00%')
  })
  it('-0.185 比率 → -18.50%(P1-3 实测 total_return)', () => {
    expect(fmtPct(-0.185)).toBe('-18.50%')
  })
  it('-0.0201 比率 → -2.01%(真机实测 drawdown)', () => {
    expect(fmtPct(-0.0201)).toBe('-2.01%')
  })
})

describe('fmtPctNum · 百分比数值不 ×100(仅 trades.return_pct)', () => {
  it('-2.76 百分比数值 → -2.76%(P1-4e.fix 真机值 · 误用 fmtPct 会变 -276.00%)', () => {
    expect(fmtPctNum(-2.76)).toBe('-2.76%')
    expect(fmtPct(-2.76)).toBe('-276.00%') // ← 反例锁死:两函数对同输入差 100 倍
  })
  it('23.52 百分比数值 → +23.52%', () => {
    expect(fmtPctNum(23.52)).toBe('+23.52%')
  })
})

describe('其余格式化(回归保护)', () => {
  it('fmtRatio:1.2 → 1.20(sharpe 类原值)', () => {
    expect(fmtRatio(1.2)).toBe('1.20')
  })
  it('fmtInt:17.0 → 17(trade_count)', () => {
    expect(fmtInt(17.0)).toBe('17')
  })
  it('fmtNum:-27547.76 → -27,547.76(pnl 绝对额 · 真机值)', () => {
    expect(fmtNum(-27547.76)).toBe('-27,547.76')
  })
})
