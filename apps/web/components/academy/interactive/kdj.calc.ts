/**
 * D13 KDJ · 纯计算逻辑(随机指标)。
 * ★ RSV = (C − Lₙ) / (Hₙ − Lₙ) × 100(常 n=9);K = SMA(RSV,3)、D = SMA(K,3)、J = 3K − 2D。
 *   此处 SMA 为中国式平滑移动平均(递归):K = (2·K_prev + RSV) / 3、D = (2·D_prev + K) / 3,初值 K=D=50。
 * ★ 超买(K/D>80)/超卖(K/D<20)是参考、非反转信号;强趋势会钝化。
 * ★ J 可超出 0~100(K、D 限于 0~100,但 J = 3K − 2D 是放大计算,会冲出区间)—— 正常,不是错误。
 * ★ KDJ 金叉(K 上穿 D)/死叉是参考、非交易指令;与均线金叉、MACD 金叉是三个不同的「金叉」。
 */
export interface KdjPoint {
  k: number
  d: number
  j: number
}
export type CrossType = 'golden' | 'death'
export interface KdjCross {
  index: number
  type: CrossType
}

/** KDJ 三线序列(递归平滑,初值 K=D=50);RSV 预热期不足 n 根时取 50 */
export function computeKdj(
  highs: number[],
  lows: number[],
  closes: number[],
  n = 9,
): KdjPoint[] {
  const out: KdjPoint[] = []
  let kPrev = 50
  let dPrev = 50
  for (let i = 0; i < closes.length; i++) {
    let rsv = 50
    if (i >= n - 1) {
      let hh = -Infinity
      let ll = Infinity
      for (let j = i - n + 1; j <= i; j++) {
        hh = Math.max(hh, highs[j])
        ll = Math.min(ll, lows[j])
      }
      rsv = hh === ll ? 50 : ((closes[i] - ll) / (hh - ll)) * 100
    }
    const k = (2 * kPrev + rsv) / 3
    const d = (2 * dPrev + k) / 3
    out.push({ k, d, j: 3 * k - 2 * d })
    kPrev = k
    dPrev = d
  }
  return out
}

/** 超买:K/D ≥ 阈值(默认 80),参考非反转 */
export function isOverbought(point: KdjPoint, threshold = 80): boolean {
  return point.k >= threshold && point.d >= threshold
}

/** 超卖:K/D ≤ 阈值(默认 20),参考非反转 */
export function isOversold(point: KdjPoint, threshold = 20): boolean {
  return point.k <= threshold && point.d <= threshold
}

/** KDJ 金叉/死叉:金叉 = K 上穿 D、死叉 = K 下穿 D */
export function detectKdjCrosses(points: KdjPoint[]): KdjCross[] {
  const out: KdjCross[] = []
  for (let i = 1; i < points.length; i++) {
    const g0 = points[i - 1].k - points[i - 1].d
    const g1 = points[i].k - points[i].d
    if (g0 <= 0 && g1 > 0) out.push({ index: i, type: 'golden' })
    else if (g0 >= 0 && g1 < 0) out.push({ index: i, type: 'death' })
  }
  return out
}
