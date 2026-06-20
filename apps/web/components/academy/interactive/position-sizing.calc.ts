/**
 * D5 1%风险法 / 仓位反推 · 纯计算逻辑(本组件核心口径:杠杆不决定单笔亏损)。
 * 流程:先定风险% → 反推名义仓位 → 再选杠杆。
 * ★ 单笔最大亏损 = 权益 × 风险%      —— 与杠杆【无关】
 * ★ 应开名义仓位 = 最大亏损 / 止损幅度% —— 与杠杆【无关】
 * ★ 占用保证金 = 名义仓位 / 杠杆       —— 与杠杆【相关】
 * 约定:riskPct / stopPct 为小数(0.01 = 1%)。
 */
export interface SizingResult {
  maxLoss: number      // 权益 × 风险%(杠杆无关)
  notional: number     // 最大亏损 / 止损%(杠杆无关)
  marginUsed: number   // 名义 / 杠杆(杠杆相关)
  liqDistPct: number   // 爆仓距 ≈ 1/杠杆(小数)
  stopSafe: boolean    // 止损是否在爆仓之前(止损% < 爆仓距%)
}

/** 单笔最大亏损 = 权益 × 风险%(不含杠杆参数:结构上即与杠杆无关) */
export function maxLoss(equity: number, riskPct: number): number {
  return equity * riskPct
}

/** 应开名义仓位 = 最大亏损 / 止损幅度%(不含杠杆参数) */
export function notionalForRisk(equity: number, riskPct: number, stopPct: number): number {
  return maxLoss(equity, riskPct) / stopPct
}

/** 占用保证金 = 名义仓位 / 杠杆(唯一与杠杆相关的量) */
export function marginUsed(notional: number, leverage: number): number {
  return notional / leverage
}

export function computeSizing(
  equity: number,
  riskPct: number,
  stopPct: number,
  leverage: number,
): SizingResult {
  const loss = maxLoss(equity, riskPct)
  const notional = loss / stopPct
  const liqDistPct = 1 / leverage
  return {
    maxLoss: loss,
    notional,
    marginUsed: notional / leverage,
    liqDistPct,
    // 止损要在爆仓之前:止损幅度% 必须小于爆仓距%(否则止损没触发就先爆仓)
    stopSafe: stopPct < liqDistPct,
  }
}
