/**
 * 滑点 + 手续费率 · 客户端镜像 0008 § 4 · 用于下单 confirm 模态实时预估。
 *
 * 跟后端 apps/api/app/services/virtual_trading/fees.py 保持同步。
 * 后端是唯一真相源,前端只做预估展示。
 */

import type { Market } from '@midas/shared'

export const SLIPPAGE_BPS: Record<Market, number> = {
  cn: 5,
  us: 3,
  crypto: 10,
  hk: 5, // 港股象征性占位 · 待定(港股暂不可下单 · P1-3+ 校准后端 fees.py)
}

export interface CommissionRates {
  buy: number
  sell: number
}

export const COMMISSION_RATES: Record<Market, CommissionRates> = {
  cn: { buy: 0.0003, sell: 0.0013 },
  us: { buy: 0, sell: 0 },
  crypto: { buy: 0.001, sell: 0.001 },
  hk: { buy: 0.001, sell: 0.0011 }, // 港股象征性占位 · 待定(含印花税概念 · P1-3+ 校准)
}

export interface OrderEstimate {
  fillPrice: number
  notional: number
  commission: number
  slippageCost: number
  totalCost: number  // buy: notional + commission · sell: notional - commission
}

export function estimateOrder(
  market: Market,
  side: 'buy' | 'sell',
  marketPrice: number,
  quantity: number,
): OrderEstimate {
  const slipBp = SLIPPAGE_BPS[market]
  const factor = side === 'buy' ? 1 + slipBp / 10000 : 1 - slipBp / 10000
  const fillPrice = marketPrice * factor
  const notional = quantity * fillPrice
  const rate = COMMISSION_RATES[market][side]
  const commission = notional * rate
  const slippageCost = Math.abs(fillPrice - marketPrice) * quantity
  const totalCost = side === 'buy' ? notional + commission : notional - commission
  return { fillPrice, notional, commission, slippageCost, totalCost }
}
