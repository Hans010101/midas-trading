/**
 * D8 爆仓全过程 · 纯计算逻辑(步进式逼近)。
 * ★ 爆仓是一步步逼近、非突然;维持保证金致【实际强平比理论(保证金归零)更早】。
 * ★ 每一步(实际强平之前)都是止损机会:仍有正权益、可主动平仓。
 * 以多单为例(entry 上方做空对称,不在本演示):价格下跌 → 权益被一格格吃掉。
 * 约定:maintenanceRate 为小数(0.005 = 0.5%);权益、保证金以"占保证金的比例"表达便于可视化。
 */
export type StepStatus = 'healthy' | 'warning' | 'liquidated'

/** 理论爆仓价(保证金归零):entry × (1 − 1/杠杆) */
export function theoreticalLiqPrice(leverage: number, entry: number): number {
  return entry * (1 - 1 / leverage)
}

/**
 * 实际爆仓价(权益触及维持保证金,比理论更早):entry × (1 − 1/杠杆 + 维持保证金率)。
 * 因为价格更高时权益就已跌到维持线 → 强平发生在更高价位 = 更早。
 */
export function actualLiqPrice(leverage: number, maintenanceRate: number, entry: number): number {
  return entry * (1 - 1 / leverage + maintenanceRate)
}

/**
 * 给定当前价,多单剩余权益占保证金的比例(1 = 满,0 = 归零)。
 * 权益比 = 1 + 杠杆 × (price − entry)/entry。
 */
export function equityRatio(price: number, leverage: number, entry: number): number {
  return 1 + leverage * ((price - entry) / entry)
}

/** 当前价的步骤状态:已到实际爆仓价→liquidated;接近(权益比≤维持率的2倍)→warning;否则 healthy */
export function stepStatus(
  price: number,
  leverage: number,
  maintenanceRate: number,
  entry: number,
): StepStatus {
  const actual = actualLiqPrice(leverage, maintenanceRate, entry)
  if (price <= actual) return 'liquidated'
  const ratio = equityRatio(price, leverage, entry)
  // 维持保证金率对应的权益比阈值 = leverage × maintenanceRate;接近它即预警
  if (ratio <= leverage * maintenanceRate * 2) return 'warning'
  return 'healthy'
}
