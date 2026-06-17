/**
 * 会员订阅档位与定价(Phase 2a 刀2)· 纯数据 + 纯函数(vitest 可钉)。
 *
 * 叙事:诚实订阅 —— 付 X 得 Pro 全部更高额度,到期自动回落免费版,无自动续费、无隐藏条款。
 * 价格如实(USDT · 与后端 PRICE_USDT 同口径 4.9/9.9/19.9)· 不夸大。
 */

export type Period = 'month' | 'quarter' | 'year'

export interface PlanTier {
  period: Period
  label: string
  months: number
  priceUsdt: string  // string 避免浮点(与后端同口径)
  highlight?: boolean
}

// ★ 与后端 app/services/payment/order.py PRICE_USDT 同口径(改价两处同步)
export const PLAN_TIERS: readonly PlanTier[] = [
  { period: 'month', label: '月度', months: 1, priceUsdt: '4.9' },
  { period: 'quarter', label: '季度', months: 3, priceUsdt: '9.9' },
  { period: 'year', label: '年度', months: 12, priceUsdt: '19.9', highlight: true },
] as const

const MONTHLY_PRICE = Number(PLAN_TIERS[0].priceUsdt)

/** 月均价折算(展示"月均 X USDT")· 2 位小数。 */
export function monthlyEquivalent(tier: Pick<PlanTier, 'priceUsdt' | 'months'>): string {
  return (Number(tier.priceUsdt) / tier.months).toFixed(2)
}

/** 相对「按月付费」省的百分比(月度本身=0)· 取整。 */
export function savingsPct(tier: Pick<PlanTier, 'priceUsdt' | 'months'>): number {
  if (tier.months <= 1) return 0
  return Math.round((1 - Number(tier.priceUsdt) / (MONTHLY_PRICE * tier.months)) * 100)
}

// Pro vs 免费版额度(与后端 PLAN_QUOTAS 同口径)
export const PRO_BENEFITS: readonly { label: string; free: string; pro: string }[] = [
  { label: 'AI 沙盘诊断', free: '5 次/月', pro: '300 次/月' },
  { label: '策略回测', free: '3 次/月', pro: '150 次/月' },
]

export const SUPPORTER_NOTE =
  '「支持者计划」是诚实订阅:按周期付费即开 Pro 全部更高额度,到期自动回落免费版 —— ' +
  '无自动续费、无隐藏条款。你的订阅直接支持点金持续打磨,而非广告或卖数据。'
