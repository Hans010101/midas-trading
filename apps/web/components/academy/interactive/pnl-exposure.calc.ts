/**
 * D7 盈亏与敞口 · 纯计算逻辑(破"只投1000最多亏1000"的致命误区)。
 * ★ 盈亏按【名义敞口 = 保证金 × 杠杆】算,【不是】按保证金算。
 * ★ 小幅反向 × 高杠杆即可击穿保证金 → 爆仓("只投1000最多亏1000"是错的)。
 * 约定:priceMovePct 为小数带符号(对多单:负=亏);亏损达到保证金即爆仓。
 */
export interface PnlResult {
  notional: number       // 保证金 × 杠杆
  pnl: number            // 名义敞口 × 价格变动%(带符号)
  pnlPctOfMargin: number // 杠杆 × 价格变动%(=盈亏/保证金,小数)
  liquidated: boolean    // 亏损 ≥ 保证金 → 爆仓
}

/** 名义敞口 = 保证金 × 杠杆 */
export function notionalExposure(margin: number, leverage: number): number {
  return margin * leverage
}

/** 浮动盈亏 = 名义敞口 × 价格变动%(★按名义算,不是按保证金算) */
export function pnl(margin: number, leverage: number, priceMovePct: number): number {
  return notionalExposure(margin, leverage) * priceMovePct
}

export function computePnl(margin: number, leverage: number, priceMovePct: number): PnlResult {
  const notional = notionalExposure(margin, leverage)
  const rawPnl = notional * priceMovePct
  return {
    notional,
    pnl: rawPnl,
    pnlPctOfMargin: leverage * priceMovePct,
    // 亏损达到/超过保证金即爆仓(反向 pnl ≤ −margin)
    liquidated: rawPnl <= -margin,
  }
}
