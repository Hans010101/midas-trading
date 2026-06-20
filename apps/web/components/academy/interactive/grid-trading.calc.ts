/**
 * D20 网格交易 · 纯计算逻辑。
 * ★ 网格 = 在区间内分层挂买卖单,价格来回波动反复成交、赚价差。
 * ★ 适合震荡市;单边行情(尤其单边下跌)是网格的天敌——越买越套(逐格浮亏加深)。
 * ★ 网格不是稳赚;区间选错、趋势突破会亏损。
 */
export interface GridTrade {
  i: number
  price: number
  type: 'buy' | 'sell'
}
export interface GridResult {
  buys: number
  sells: number
  realized: number // 已实现价差收益
  openLots: number // 未平仓持仓手数(单边行情下堆积)
  trades: GridTrade[] // 成交明细(用于可视化标注)
}

/** 等分网格价位(count 格 → count+1 条线) */
export function gridLevels(lower: number, upper: number, count: number): number[] {
  const step = (upper - lower) / count
  return Array.from({ length: count + 1 }, (_, i) => lower + i * step)
}

/** 模拟网格成交:下穿格线买入、上穿格线卖出(配对赚一格价差);返回成交与持仓 */
export function simulateGrid(lower: number, upper: number, count: number, prices: number[]): GridResult {
  const levels = gridLevels(lower, upper, count)
  const step = (upper - lower) / count
  const open: number[] = []
  const trades: GridTrade[] = []
  let realized = 0
  let buys = 0
  let sells = 0
  let prev = prices[0]
  for (let t = 1; t < prices.length; t++) {
    const cur = prices[t]
    for (const lv of levels) {
      if (prev > lv && cur <= lv) {
        open.push(lv)
        buys++
        trades.push({ i: t, price: lv, type: 'buy' })
      }
    }
    for (const lv of levels) {
      if (prev < lv && cur >= lv) {
        const idx = open.findIndex((b) => b <= lv - step + 1e-9)
        if (idx >= 0) {
          realized += step
          open.splice(idx, 1)
          sells++
          trades.push({ i: t, price: lv, type: 'sell' })
        }
      }
    }
    prev = cur
  }
  return { buys, sells, realized, openLots: open.length, trades }
}
