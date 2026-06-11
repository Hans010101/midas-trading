/**
 * 条件单纯逻辑(ADR 0041 刀3)· 与后端触发矩阵同口径 · vitest 可测。
 *
 * 🔴 红线:这里只做【前端提示用】的预判与展示映射,真正的触发判断在后端
 *   conditional_trigger.should_trigger(60s 扫描)· 前端绝不撮合。
 */

import type { OrderSide, PositionSide } from '@/lib/api/virtual'

export type ConditionalKind = 'limit' | 'stop_loss' | 'take_profit'
export type ConditionalStatus = 'active' | 'triggered' | 'cancelled' | 'expired'

/** 类型中文(LIMIT 按 side 细分:限价买入 / 限价卖出)。 */
export function kindLabel(kind: ConditionalKind, side: OrderSide): string {
  if (kind === 'limit') return side === 'buy' ? '限价买入' : '限价卖出'
  return kind === 'stop_loss' ? '止损' : '止盈'
}

export const STATUS_ZH: Record<ConditionalStatus, string> = {
  active: '待触发',
  triggered: '已触发',
  cancelled: '已撤销',
  expired: '已失效',
}

/**
 * 触发矩阵预判(与后端 should_trigger 同矩阵 · 全含等号)。
 * 仅用于挂单前提示「当前价已满足触发条件,挂单后约 1 分钟内即会成交」——
 * LIMIT BUY 触发价高于现价会立即触发是语义非 bug,提前告知用户。
 */
export function wouldTriggerNow(
  kind: ConditionalKind,
  side: OrderSide,
  positionSide: PositionSide,
  triggerPrice: number,
  price: number,
): boolean {
  if (kind === 'limit') {
    return side === 'buy' ? price <= triggerPrice : price >= triggerPrice
  }
  const closingLong = positionSide === 'long'
  if (kind === 'stop_loss') {
    return closingLong ? price <= triggerPrice : price >= triggerPrice
  }
  // take_profit
  return closingLong ? price >= triggerPrice : price <= triggerPrice
}

/** 触发价相对现价的偏离百分比(绝对值)· 现价无效返回 null。 */
export function deviationPct(triggerPrice: number, currentPrice: number | null): number | null {
  if (currentPrice == null || currentPrice <= 0 || !Number.isFinite(triggerPrice)) return null
  return Math.abs((triggerPrice - currentPrice) / currentPrice) * 100
}
