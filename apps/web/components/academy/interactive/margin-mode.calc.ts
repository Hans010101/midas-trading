/**
 * D6 保证金模式(全仓/逐仓)· 纯计算逻辑。
 * ★ 逐仓:亏损限于【该仓保证金】,爆仓只损失该仓;爆仓价 = 开仓价 × (1 ∓ 1/杠杆)(与 D1 同)。
 * ★ 全仓:用【整个账户余额】抵抗,爆仓价【更远】(缓冲更大),但爆仓影响【全部】。
 * 多单爆仓价在开仓价下方、空单在上方;全仓比逐仓更靠外。
 * 约定:notional = positionMargin × leverage;accountEquity > positionMargin(账户里还有别的钱)。
 */
export type Side = 'long' | 'short'
export type MarginMode = 'isolated' | 'cross'

/** 逐仓爆仓价:只有该仓保证金抵抗 → entry × (1 ∓ 1/杠杆) */
export function isolatedLiqPrice(side: Side, leverage: number, entry: number): number {
  const inv = 1 / leverage
  return side === 'long' ? entry * (1 - inv) : entry * (1 + inv)
}

/**
 * 全仓爆仓价:整个账户余额抵抗 → 缓冲 = accountEquity / notional(> 1/杠杆)。
 * 多单 entry × (1 − equity/notional)、空单 entry × (1 + equity/notional);多单不低于 0。
 */
export function crossLiqPrice(
  side: Side,
  leverage: number,
  entry: number,
  positionMargin: number,
  accountEquity: number,
): number {
  const notional = positionMargin * leverage
  const buffer = accountEquity / notional
  const raw = side === 'long' ? entry * (1 - buffer) : entry * (1 + buffer)
  return side === 'long' ? Math.max(0, raw) : raw
}

/** 逐仓最大亏损 = 该仓保证金(亏损被隔离、封顶) */
export function isolatedMaxLoss(positionMargin: number): number {
  return positionMargin
}

/** 全仓最大亏损 = 整个账户余额(爆仓影响全部) */
export function crossMaxLoss(accountEquity: number): number {
  return accountEquity
}
