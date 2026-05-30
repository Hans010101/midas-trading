/**
 * 金额格式化 · 0008 v2 三独立子账户 · 各市场原币种,不折算。
 *
 * - cn / CNY → ¥
 * - us / USD → $
 * - crypto / USDT → USDT 后缀
 */

import type { Market } from '@midas/shared'
import type { Currency } from '@/lib/api/virtual'

export const CURRENCY_SYMBOL: Record<Currency, string> = {
  CNY: '¥',
  USD: '$',
  USDT: 'USDT',
  HKD: 'HK$',
}

export const MARKET_CURRENCY: Record<Market, Currency> = {
  cn: 'CNY',
  us: 'USD',
  crypto: 'USDT',
  hk: 'HKD',
}

export const MARKET_LABEL: Record<Market, string> = {
  cn: 'A 股',
  us: '美股',
  crypto: '加密',
  hk: '港股',
}

/**
 * 格式化金额 + 货币符号。
 * - CNY / USD:符号前置,千分位,默认 2 位小数
 * - USDT:数字 + 后缀 ' USDT'
 *
 * 输入是字符串(后端 Decimal 序列化),返回展示字符串。
 */
export function formatMoney(
  amount: string | number,
  currency: Currency,
  options: { decimals?: number; sign?: boolean } = {},
): string {
  const num = typeof amount === 'string' ? Number(amount) : amount
  const decimals = options.decimals ?? (currency === 'USDT' ? 4 : 2)
  const formatted = num.toLocaleString('en-US', {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  })
  const signed = options.sign && num > 0 ? `+${formatted}` : formatted

  if (currency === 'USDT') {
    return `${signed} USDT`
  }
  return `${CURRENCY_SYMBOL[currency]}${signed}`
}

/** 给市场返回货币符号。 */
export function currencyOf(market: Market): Currency {
  return MARKET_CURRENCY[market]
}

/** 格式化百分比 · 涨跌幅。 */
export function formatPct(pct: number): string {
  const sign = pct >= 0 ? '+' : ''
  return `${sign}${pct.toFixed(2)}%`
}
