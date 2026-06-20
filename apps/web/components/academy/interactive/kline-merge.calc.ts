/**
 * D14 K线合并(缠论包含处理)· 纯计算逻辑。
 * ★ 包含关系 = 一根 K 的高低点完全被相邻 K 包住(高≥高 且 低≤低,或反向)。
 * ★ 向上处理取「高高」(高点取高者、低点也取高者);向下处理取「低低」(高点取低者、低点也取低者)。
 * 合并是缠论预处理第一步,让后续分型/笔判断干净。
 */
export interface Kline {
  high: number
  low: number
}
export type Direction = 'up' | 'down'

/** 两根 K 是否存在包含关系(任一方包住另一方) */
export function hasContainment(a: Kline, b: Kline): boolean {
  return (a.high >= b.high && a.low <= b.low) || (b.high >= a.high && b.low <= a.low)
}

/** 合并两根有包含关系的 K:向上取「高高」、向下取「低低」 */
export function mergeKline(a: Kline, b: Kline, direction: Direction): Kline {
  if (direction === 'up') {
    return { high: Math.max(a.high, b.high), low: Math.max(a.low, b.low) }
  }
  return { high: Math.min(a.high, b.high), low: Math.min(a.low, b.low) }
}
