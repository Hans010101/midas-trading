/**
 * D18 盈亏比 · 纯计算逻辑。
 * ★ 盈亏比 = 潜在盈利 / 潜在亏损(= 止盈距离 / 止损距离)。
 * ★ 盈亏比与胜率共同决定长期期望:高盈亏比可容忍低胜率,反之亦然。
 * ★ 盈亏比本身不保证盈利(还要看胜率与执行);高盈亏比 ≠ 高胜率。
 */

/** 盈亏比 = 止盈距离 / 止损距离 */
export function riskRewardRatio(takeProfitDist: number, stopLossDist: number): number {
  return takeProfitDist / stopLossDist
}

/** 期望(以止损=1单位计):胜率×盈亏比 − 败率×1 */
export function expectancy(winRate: number, rrRatio: number): number {
  return winRate * rrRatio - (1 - winRate) * 1
}

/** 保本胜率 = 1 / (1 + 盈亏比)(期望=0 时所需胜率) */
export function breakEvenWinRate(rrRatio: number): number {
  return 1 / (1 + rrRatio)
}
