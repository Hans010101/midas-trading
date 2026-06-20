/**
 * D21 马丁格尔 · 纯计算逻辑(★★反面演示,绝不是可用策略)。
 * ★★ 马丁格尔 = 亏损后加倍下注试图一次回本;有限资金下【必然爆仓】。
 * ★★ 本模块仅用于演示其危险:下注额指数膨胀 → 累计投入指数膨胀 → 爆仓归零。
 *     不得用于任何「能回本/能稳赚」的暗示。
 */

/** 第 n 次连亏后的下注额(从 0 计):base × 2^n —— 指数膨胀 */
export function betAtStreak(base: number, lossStreak: number): number {
  return base * Math.pow(2, lossStreak)
}

/** 连亏 n 次的累计投入(等比和):base × (2^(n+1) − 1) */
export function cumulativeStake(base: number, lossStreak: number): number {
  return base * (Math.pow(2, lossStreak + 1) - 1)
}

/** 有限本金下,连亏到第几次累计投入将超过本金(必然存在 → 必爆仓) */
export function bustStreak(capital: number, base: number): number {
  let n = 0
  while (cumulativeStake(base, n) <= capital) n++
  return n
}
