/**
 * D19 趋势与震荡 · 纯计算逻辑。
 * ★ 上升趋势 = 摆动高点与低点都依次抬高;下降趋势 = 都依次降低;否则 = 震荡。
 * ★ 不同市态适用不同方法(趋势顺势 / 震荡高抛低吸);用错市态会反复挨打。
 * ★ 市态判断是参考,事后清晰、事前难判,无完美识别。
 */
export type MarketType = 'uptrend' | 'downtrend' | 'range'

function strictlyUp(xs: number[]): boolean {
  for (let i = 1; i < xs.length; i++) if (xs[i] <= xs[i - 1]) return false
  return true
}
function strictlyDown(xs: number[]): boolean {
  for (let i = 1; i < xs.length; i++) if (xs[i] >= xs[i - 1]) return false
  return true
}

/** 由摆动高点序列与低点序列判定市态 */
export function classifyMarket(swingHighs: number[], swingLows: number[]): MarketType {
  if (strictlyUp(swingHighs) && strictlyUp(swingLows)) return 'uptrend'
  if (strictlyDown(swingHighs) && strictlyDown(swingLows)) return 'downtrend'
  return 'range'
}
