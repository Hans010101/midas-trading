/**
 * D11 布林带 · 纯计算逻辑。
 * ★ 中轨 = MA(20)；上轨 = 中轨 + K×σ；下轨 = 中轨 − K×σ（K=2，上下对称）。
 * ★ σ = N 周期收盘价标准差（总体标准差，分母 N）。
 * 触轨非反转信号；强趋势会沿轨运行（开口）；带宽反映波动率。
 */
export interface BollBand {
  mid: number | null
  upper: number | null
  lower: number | null
}

/** 简单均线 SMA(N)，不足 N 根为 null */
export function sma(closes: number[], n: number): (number | null)[] {
  const out: (number | null)[] = []
  for (let i = 0; i < closes.length; i++) {
    if (i < n - 1) {
      out.push(null)
      continue
    }
    let sum = 0
    for (let j = i - n + 1; j <= i; j++) sum += closes[j]
    out.push(sum / n)
  }
  return out
}

/** N 周期总体标准差（分母 N），不足 N 根为 null */
export function stddev(closes: number[], n: number): (number | null)[] {
  const out: (number | null)[] = []
  for (let i = 0; i < closes.length; i++) {
    if (i < n - 1) {
      out.push(null)
      continue
    }
    let sum = 0
    for (let j = i - n + 1; j <= i; j++) sum += closes[j]
    const mean = sum / n
    let v = 0
    for (let j = i - n + 1; j <= i; j++) v += (closes[j] - mean) ** 2
    out.push(Math.sqrt(v / n))
  }
  return out
}

/** 布林带三轨：中轨 = SMA(n)、上/下轨 = 中轨 ± k×σ（k=2 对称） */
export function bollingerBands(closes: number[], n = 20, k = 2): BollBand[] {
  const mid = sma(closes, n)
  const sd = stddev(closes, n)
  return closes.map((_, i) => {
    const m = mid[i]
    const s = sd[i]
    if (m == null || s == null) return { mid: null, upper: null, lower: null }
    return { mid: m, upper: m + k * s, lower: m - k * s }
  })
}

/** 带宽 =（上轨 − 下轨）/ 中轨（反映波动率；开口大 = 波动大） */
export function bandwidth(band: BollBand): number | null {
  if (band.mid == null || band.upper == null || band.lower == null) return null
  return (band.upper - band.lower) / band.mid
}
