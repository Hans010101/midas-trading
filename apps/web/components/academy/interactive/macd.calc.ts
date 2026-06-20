/**
 * D10 MACD 金叉 · 纯计算逻辑。
 * ★ DIF = EMA(12) − EMA(26)；DEA = EMA(DIF, 9)（信号线）；MACD 柱 = (DIF − DEA) × 2。
 * ★ MACD 金叉 = DIF【上穿】DEA（不是均线、不是价格）；死叉 = DIF 下穿 DEA。
 * ★ 与 D9 区分：这里判定的是 DIF vs DEA 两条派生线，不是两条价格均线。
 * 柱正红负绿（A 股惯例）；参考、非交易指令。
 */
export interface MacdPoint {
  dif: number
  dea: number
  hist: number
}
export type CrossType = 'golden' | 'death'
export interface MacdCross {
  index: number
  type: CrossType
}

/** EMA 序列：EMA_t = α·price_t + (1−α)·EMA_{t−1}，α = 2/(n+1)；首值取 price[0]（预热期前段偏差属正常） */
export function ema(values: number[], n: number): number[] {
  const a = 2 / (n + 1)
  const out: number[] = []
  for (let i = 0; i < values.length; i++) {
    out.push(i === 0 ? values[0] : a * values[i] + (1 - a) * out[i - 1])
  }
  return out
}

/** MACD 三件套：DIF = EMA(fast) − EMA(slow)、DEA = EMA(DIF, signal)、柱 = (DIF − DEA) × 2 */
export function computeMacd(closes: number[], fast = 12, slow = 26, signal = 9): MacdPoint[] {
  const emaFast = ema(closes, fast)
  const emaSlow = ema(closes, slow)
  const dif = closes.map((_, i) => emaFast[i] - emaSlow[i])
  const dea = ema(dif, signal)
  return closes.map((_, i) => ({
    dif: dif[i],
    dea: dea[i],
    hist: (dif[i] - dea[i]) * 2,
  }))
}

/** MACD 金叉/死叉：金叉 = DIF 上穿 DEA、死叉 = DIF 下穿 DEA */
export function detectMacdCrosses(points: MacdPoint[]): MacdCross[] {
  const out: MacdCross[] = []
  for (let i = 1; i < points.length; i++) {
    const d0 = points[i - 1].dif - points[i - 1].dea
    const d1 = points[i].dif - points[i].dea
    if (d0 <= 0 && d1 > 0) out.push({ index: i, type: 'golden' })
    else if (d0 >= 0 && d1 < 0) out.push({ index: i, type: 'death' })
  }
  return out
}
