/**
 * D1 爆仓价 · 纯计算逻辑(可单测,口径钉死)。
 * 多单爆仓价在开仓价【下方】、空单在【上方】;杠杆越高越贴近开仓价。
 * 逐仓理论近似(忽略维持保证金/手续费/资金费/滑点)——实际强平更早,UI 另标注。
 */
export type Side = 'long' | 'short'

/** 教学固定开仓价 */
export const ENTRY_PRICE = 100

/**
 * 理论爆仓价。
 * 多单:entry × (1 − 1/leverage)(开仓价下方)
 * 空单:entry × (1 + 1/leverage)(开仓价上方)
 */
export function liquidationPrice(side: Side, leverage: number, entry: number = ENTRY_PRICE): number {
  const inv = 1 / leverage
  return side === 'long' ? entry * (1 - inv) : entry * (1 + inv)
}

/** 距开仓价的百分比(正数,即容错空间大小) */
export function bufferPct(side: Side, leverage: number, entry: number = ENTRY_PRICE): number {
  const liq = liquidationPrice(side, leverage, entry)
  return (Math.abs(entry - liq) / entry) * 100
}
