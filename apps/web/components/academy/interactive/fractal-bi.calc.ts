/**
 * D15 分型与笔(缠论)· 纯计算逻辑。
 * ★ 顶分型 = 连续三根 K 里中间一根的高点最高、且低点也最高(中间 K 整体最高)。
 * ★ 底分型 = 中间一根的低点最低、且高点也最低。
 * ★ 笔 = 相邻的顶分型与底分型之间的连接(顶底交替)。
 * 分型/笔是结构骨架,不是买卖信号。
 */
export interface Kline {
  high: number
  low: number
}
export type FractalType = 'top' | 'bottom'
export interface Fractal {
  index: number
  type: FractalType
}
export interface Bi {
  fromIndex: number
  toIndex: number
  direction: 'up' | 'down'
}

/** 检测顶/底分型(中间 K 高低点都最高=顶;都最低=底) */
export function detectFractals(klines: Kline[]): Fractal[] {
  const out: Fractal[] = []
  for (let i = 1; i < klines.length - 1; i++) {
    const p = klines[i - 1]
    const c = klines[i]
    const n = klines[i + 1]
    if (c.high > p.high && c.high > n.high && c.low > p.low && c.low > n.low) {
      out.push({ index: i, type: 'top' })
    } else if (c.low < p.low && c.low < n.low && c.high < p.high && c.high < n.high) {
      out.push({ index: i, type: 'bottom' })
    }
  }
  return out
}

/** 由顶底分型连成笔(相邻不同类型分型连接;底→顶为上升笔、顶→底为下降笔) */
export function buildBi(fractals: Fractal[]): Bi[] {
  const out: Bi[] = []
  for (let i = 1; i < fractals.length; i++) {
    const a = fractals[i - 1]
    const b = fractals[i]
    if (a.type !== b.type) {
      out.push({ fromIndex: a.index, toIndex: b.index, direction: a.type === 'bottom' ? 'up' : 'down' })
    }
  }
  return out
}
