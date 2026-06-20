/**
 * D12 RSI · 纯计算逻辑（教学重点：钝化）。
 * ★ RSI = 100 − 100/(1 + RS)；RS = N 周期平均涨幅 / N 周期平均跌幅（常 N=14）。
 * ★ 超买（70）/超卖（30）是参考、非反转信号。
 * ★ 钝化：强趋势中 RSI 可长期贴在超买/超卖区（高位/低位钝化），不代表立即反转。
 * 约定：用 N 周期简单平均（便于教学）；全涨 → RSI=100、全跌 → RSI=0。
 */
export type Zone = 'overbought' | 'oversold'

/** RSI 序列（简单平均口径）；前 N 根不足为 null */
export function computeRsi(closes: number[], n = 14): (number | null)[] {
  const out: (number | null)[] = []
  for (let i = 0; i < closes.length; i++) {
    if (i < n) {
      out.push(null)
      continue
    }
    let gain = 0
    let loss = 0
    for (let j = i - n + 1; j <= i; j++) {
      const change = closes[j] - closes[j - 1]
      if (change > 0) gain += change
      else loss += -change
    }
    const avgGain = gain / n
    const avgLoss = loss / n
    if (avgLoss === 0) {
      out.push(100) // 全涨 → 100
      continue
    }
    if (avgGain === 0) {
      out.push(0) // 全跌 → 0
      continue
    }
    const rs = avgGain / avgLoss
    out.push(100 - 100 / (1 + rs))
  }
  return out
}

/** 超买：RSI ≥ 阈值（默认 70），参考非反转 */
export function isOverbought(rsi: number, threshold = 70): boolean {
  return rsi >= threshold
}

/** 超卖：RSI ≤ 阈值（默认 30），参考非反转 */
export function isOversold(rsi: number, threshold = 30): boolean {
  return rsi <= threshold
}

/**
 * 钝化检测：是否存在连续 count 根 RSI 停留在超买（或超卖）区。
 * 强趋势中 RSI 钝化贴顶/贴底，不代表反转。
 */
export function isBlunted(
  rsiSeries: (number | null)[],
  threshold: number,
  count: number,
  zone: Zone,
): boolean {
  let run = 0
  for (const r of rsiSeries) {
    if (r == null) {
      run = 0
      continue
    }
    const inZone = zone === 'overbought' ? r >= threshold : r <= threshold
    if (inZone) {
      run++
      if (run >= count) return true
    } else {
      run = 0
    }
  }
  return false
}
