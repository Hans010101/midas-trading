/**
 * D2 缠论中枢 · 纯计算逻辑(口径最严,单测含显式反测)。
 * ★ 上沿 ZG = 三段高点的【最小值】;下沿 ZD = 三段低点的【最大值】(绝不能取反)。
 * ★ 仅当 ZD < ZG(三段有共同重叠区)才构成中枢;ZD == ZG(相切不重叠)判不构成。
 */
export interface PivotResult {
  zg: number      // 上沿 = min(highs)
  zd: number      // 下沿 = max(lows)
  formed: boolean // ZD < ZG 才成中枢
}

export function computePivot(highs: number[], lows: number[]): PivotResult {
  const zg = Math.min(...highs)
  const zd = Math.max(...lows)
  return { zg, zd, formed: zd < zg }
}
