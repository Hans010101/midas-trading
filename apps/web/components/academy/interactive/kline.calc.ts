/**
 * D3 K线构成 · 纯计算逻辑。
 * 实体 = 开↔收;上影 = 实体顶→最高;下影 = 实体底→最低。
 * 约束:最高 ≥ max(开,收)、最低 ≤ min(开,收)。
 * ★ 配色口径(国内习惯):阳线(收>开)红、阴线(收<开)绿、十字星(收≈开)实体极小。
 *   组件用 up/down 语义 token 上色(默认红涨绿跌);此处只判类型、不绑死颜色。
 */
export type CandleType = 'yang' | 'yin' | 'doji'

export interface OHLC {
  open: number
  high: number
  low: number
  close: number
}

export interface CandleGeometry {
  bodyTop: number
  bodyBottom: number
  upperShadow: number
  lowerShadow: number
  type: CandleType
}

/** 十字星阈值:|收−开| ≤ epsilon 视为十字星(示意阈值) */
export const DOJI_EPSILON = 0.5

export function classifyCandle(open: number, close: number, epsilon: number = DOJI_EPSILON): CandleType {
  if (close - open > epsilon) return 'yang'
  if (open - close > epsilon) return 'yin'
  return 'doji'
}

/** 约束最高:不得低于实体顶 max(开,收) */
export function clampHigh(high: number, open: number, close: number): number {
  return Math.max(high, open, close)
}

/** 约束最低:不得高于实体底 min(开,收) */
export function clampLow(low: number, open: number, close: number): number {
  return Math.min(low, open, close)
}

export function candleGeometry(ohlc: OHLC, epsilon: number = DOJI_EPSILON): CandleGeometry {
  const { open, close } = ohlc
  const high = clampHigh(ohlc.high, open, close)
  const low = clampLow(ohlc.low, open, close)
  const bodyTop = Math.max(open, close)
  const bodyBottom = Math.min(open, close)
  return {
    bodyTop,
    bodyBottom,
    upperShadow: high - bodyTop,
    lowerShadow: bodyBottom - low,
    type: classifyCandle(open, close, epsilon),
  }
}
