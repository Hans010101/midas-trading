/**
 * 条件单纯逻辑(ADR 0041 刀3)· 与后端触发矩阵同口径 · vitest 可测。
 *
 * 🔴 红线:这里只做【前端提示用】的预判与展示映射,真正的触发判断在后端
 *   conditional_trigger.should_trigger(60s 扫描)· 前端绝不撮合。
 */

import type { OrderSide, PositionSide } from '@/lib/api/virtual'

export type ConditionalKind = 'limit' | 'stop_loss' | 'take_profit'
export type ConditionalStatus = 'active' | 'triggered' | 'cancelled' | 'expired'

// perp 限价开仓杠杆范围 · 与后端 schema(ge=1 le=125)同口径。
// 注:故意与 perp 市价表单的 PERP_MAX_LEVERAGE(=20)解耦 —— 限价单走后端完整 1-125。
export const PERP_LIMIT_MIN_LEVERAGE = 1
export const PERP_LIMIT_MAX_LEVERAGE = 125

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

/**
 * perp 限价开仓表单校验(二期刀3 · 纯函数 · 与后端端点同口径)。
 * 杠杆 1-125(后端 schema 口径)· margin>0 · margin_mode∈{cross,isolated} · 触发价>0。
 * 返回 null = 通过;否则返回首个错误中文(可提交即 null)。
 */
export function validatePerpLimit(input: {
  triggerPrice: number
  leverage: number
  margin: number
  marginMode: string
}): string | null {
  if (!(input.triggerPrice > 0)) return '请填写触发价'
  if (
    !Number.isInteger(input.leverage)
    || input.leverage < PERP_LIMIT_MIN_LEVERAGE
    || input.leverage > PERP_LIMIT_MAX_LEVERAGE
  ) {
    return `杠杆需在 ${PERP_LIMIT_MIN_LEVERAGE}-${PERP_LIMIT_MAX_LEVERAGE}x`
  }
  if (!(input.margin > 0)) return '请填写保证金'
  if (input.marginMode !== 'cross' && input.marginMode !== 'isolated') {
    return '请选择保证金模式'
  }
  return null
}

/** 触发价相对现价的偏离百分比(绝对值)· 现价无效返回 null。 */
export function deviationPct(triggerPrice: number, currentPrice: number | null): number | null {
  if (currentPrice == null || currentPrice <= 0 || !Number.isFinite(triggerPrice)) return null
  return Math.abs((triggerPrice - currentPrice) / currentPrice) * 100
}

/**
 * 快捷档位方向(+1 现价上方 / −1 现价下方)—— 永远取【不立即触发】的一侧,
 * 恰为 wouldTriggerNow 矩阵的反方向(单测互证):
 *   STOP_LOSS  平多 −1(下方)· 平空 +1(上方)
 *   TAKE_PROFIT 平多 +1(上方)· 平空 −1(下方)
 *   LIMIT buy −1(挂更低买价)· sell +1(挂更高卖价)
 */
export function presetDirection(
  kind: ConditionalKind,
  side: OrderSide,
  positionSide: PositionSide,
): 1 | -1 {
  if (kind === 'limit') return side === 'buy' ? -1 : 1
  const closingLong = positionSide === 'long'
  if (kind === 'stop_loss') return closingLong ? -1 : 1
  // take_profit
  return closingLong ? 1 : -1
}

/**
 * 快捷档位触发价:现价 ×(1 ± pct),按 presetDirection 取不立即触发的一侧。
 * 精度按现价小数位对齐(<1 的小币固定展开 8 位再去尾零,绝不截断成 0)。
 */
export function presetTriggerPrice(
  kind: ConditionalKind,
  side: OrderSide,
  positionSide: PositionSide,
  currentPrice: number,
  pct: number,
): string {
  const raw = currentPrice * (1 + presetDirection(kind, side, positionSide) * pct)
  const refDecimals = (String(currentPrice).split('.')[1] ?? '').length
  const decimals = currentPrice < 1 ? Math.max(refDecimals, 8) : Math.max(refDecimals, 2)
  // toFixed 保精度 · Number→String 去尾零(0.08502500 → 0.085025)
  return String(Number(raw.toFixed(Math.min(decimals, 12))))
}
