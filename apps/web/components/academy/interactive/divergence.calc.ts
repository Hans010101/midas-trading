/**
 * D16 背驰(缠论)· 纯计算逻辑。
 * ★ 背驰 = 价格创新高(新低)但指标力度(如 MACD 柱面积/峰值)未同步创新高(新低),表示趋势动能衰减。
 * ★ 背驰是力度比较、是参考,不是反转信号;背驰后可能盘整可能反转,不保证、不预测。
 */
export type DivergenceType = 'top' | 'bottom' | 'none'

/**
 * 比较相邻两个同向波段的价格极值与力度,判定背驰。
 * kind='high':后段价格创新高(B>A)但力度更弱(B<A)→ 顶背驰。
 * kind='low' :后段价格创新低(B<A)但力度更弱(|B|<|A|)→ 底背驰。
 */
export function detectDivergence(
  priceExtremeA: number,
  forceA: number,
  priceExtremeB: number,
  forceB: number,
  kind: 'high' | 'low',
): DivergenceType {
  if (kind === 'high') {
    if (priceExtremeB > priceExtremeA && forceB < forceA) return 'top'
    return 'none'
  }
  if (priceExtremeB < priceExtremeA && Math.abs(forceB) < Math.abs(forceA)) return 'bottom'
  return 'none'
}
