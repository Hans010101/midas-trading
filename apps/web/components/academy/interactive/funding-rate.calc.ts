/**
 * D4 资金费率 · 纯计算逻辑(口径最易记反,单测含显式反测)。
 * ★ 正费率 = 多头【付】空头;负费率 = 空头【付】多头(绝不取反)。
 * ★ 资金费是多空之间的收付、【不是】平台手续费;长期持仓 = 持有成本(按结算次数累计)。
 * 约定:rate 为小数(0.0001 = 0.01%);单次结算金额 = 名义仓位 × rate(带符号,正=多头付出)。
 */
export type FundingPayer = 'long' | 'short' | 'none'

/** 谁付费:正费率多头付、负费率空头付、零费率无人付 */
export function fundingPayer(rate: number): FundingPayer {
  if (rate > 0) return 'long'
  if (rate < 0) return 'short'
  return 'none'
}

/**
 * 单次结算金额(带符号):名义仓位 × 费率。
 * 正数 = 多头付给空头的金额;负数 = 空头付给多头(绝对值为实际付出额)。
 */
export function fundingPayment(notional: number, rate: number): number {
  return notional * rate
}

/** 付费方单次实际付出额(恒为非负):|名义 × 费率| */
export function payerAmount(notional: number, rate: number): number {
  return Math.abs(notional * rate)
}

/** 持有 settlements 次结算后,付费方的累计持有成本(恒为非负) */
export function cumulativeCost(notional: number, rate: number, settlements: number): number {
  return Math.abs(notional * rate) * settlements
}
