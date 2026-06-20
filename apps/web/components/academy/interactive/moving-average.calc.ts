/**
 * D9 均线 / 金叉死叉 · 纯计算逻辑。
 * ★ MA(N) = 最近 N 根收盘价的算术平均（滞后指标）。
 * ★ 均线金叉 = 短期均线【上穿】长期均线（如 MA5 上穿 MA20）→ 看涨参考；死叉 = 短期下穿长期。
 * ★ 与 D10 严格区分：这是【均线】金叉（两条价格均线），不是 MACD 金叉（DIF 上穿 DEA）。
 * 金叉/死叉是参考、非交易指令。
 */
export type CrossType = 'golden' | 'death'
export interface MaCross {
  index: number
  type: CrossType
}

/** MA(N)：每个位置最近 N 根收盘价算术平均；不足 N 根的位置为 null */
export function movingAverage(closes: number[], n: number): (number | null)[] {
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

/**
 * 检测两条均线的交叉点（均线金叉/死叉）。
 * 金叉 = 短期【上穿】长期（前一根 short ≤ long，当前 short > long）。
 * 死叉 = 短期【下穿】长期（前一根 short ≥ long，当前 short < long）。
 * 仅在该位置与前一位置两条线都有值时判定。
 */
export function detectMaCrosses(short: (number | null)[], long: (number | null)[]): MaCross[] {
  const out: MaCross[] = []
  for (let i = 1; i < short.length; i++) {
    const s0 = short[i - 1]
    const l0 = long[i - 1]
    const s1 = short[i]
    const l1 = long[i]
    if (s0 == null || l0 == null || s1 == null || l1 == null) continue
    if (s0 <= l0 && s1 > l1) out.push({ index: i, type: 'golden' })
    else if (s0 >= l0 && s1 < l1) out.push({ index: i, type: 'death' })
  }
  return out
}
