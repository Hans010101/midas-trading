/**
 * 铂金自助页纯展示 helper(多账户 PR-6)· 可 vitest。
 *
 * ★配色硬编码、与 admin 看板口径一致(红线③):
 *   · 盈亏 = 涨红跌绿(A 股·盈利红/亏损绿)
 *   · 方向 = 西式(做多绿/做空红)· 与涨红跌绿解耦 · ★绝不用会随用户涨跌偏好翻转的 DirectionBadge
 *   · 共振分 = 正偏多绿/负偏空红/0 中性金
 */

/** 盈亏上色(盈利红 / 亏损绿 / 0 中性)。 */
export function pnlTone(v: number): string {
  return v > 0 ? 'text-rose-600' : v < 0 ? 'text-emerald-700' : 'text-muted-foreground'
}

/** ★方向上色(做多绿 / 做空红 · 西式 · 不随涨跌偏好翻转)。 */
export function sideTone(side: string): string {
  return side === 'long' ? 'text-emerald-700' : 'text-rose-600'
}

/** 方向中文(long→做多 / 其它→做空)。 */
export const sideLabel = (side: string): string => (side === 'long' ? '做多' : '做空')

/** 共振分上色(正偏多绿 / 负偏空红 / 0 中性金)。 */
export function scoreTone(v: number): string {
  return v > 0 ? 'text-emerald-700' : v < 0 ? 'text-rose-600' : 'text-gold'
}

/** 智能交易平仓原因中文。 */
export const INTEL_REASON_LABEL: Record<string, string> = {
  stop_loss: '止损',
  take_profit: '止盈',
  signal_reversal: '信号反转',
}

/** 托管交易平仓原因中文。 */
export const MANAGED_REASON_LABEL: Record<string, string> = {
  tp: '止盈',
  signal: '信号',
  timeout: '超时',
  manual: '手动',
}

/** 持仓时长(秒 → "Xh Ym")。 */
export function holdLabel(sec: number): string {
  return `${Math.floor(sec / 3600)}h${Math.floor((sec % 3600) / 60)}m`
}
