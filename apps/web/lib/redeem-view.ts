/**
 * 兑换码展示纯逻辑(兑换码刀2)· vitest 可测。
 * 三态错误解析(后端结构化 detail · 形状不符走通用,不误判)+ 文案 + 复制拼接。
 */

import type { RedeemPeriod, RedeemResult, RedeemStatus } from '@/lib/api/redeem'

export const PERIOD_LABEL: Record<string, string> = {
  month: '月卡',
  quarter: '季卡',
  year: '年卡',
}

export const PERIOD_OPTIONS: { key: RedeemPeriod; label: string }[] = [
  { key: 'month', label: '月卡(30天)' },
  { key: 'quarter', label: '季卡(90天)' },
  { key: 'year', label: '年卡(365天)' },
]

export function periodLabel(period: string): string {
  return PERIOD_LABEL[period] ?? period
}

export const STATUS_LABEL: Record<RedeemStatus, string> = {
  unused: '未用',
  redeemed: '已用',
  expired: '已过期',
}

/** 状态色:未用=墨绿(可用)· 已用/已过期=灰。 */
export function statusClass(status: RedeemStatus): string {
  return status === 'unused' ? 'text-down' : 'text-muted-foreground/60'
}

// ── 兑换三态错误解析(后端 {error, message} · 严格校验形状,不误判)──
const REDEEM_ERROR_TEXT: Record<string, string> = {
  not_found: '兑换码无效',
  already_used: '该兑换码已被使用',
  expired: '兑换码已过期',
}

/** 从后端 detail 提取友好文案;形状不符(非 {error:string})→ null(走通用)。 */
export function redeemErrorText(detail: unknown): string | null {
  if (typeof detail !== 'object' || detail === null) return null
  const d = detail as Record<string, unknown>
  if (typeof d.error !== 'string') return null
  return REDEEM_ERROR_TEXT[d.error] ?? null
}

/** 兑换成功 toast 文案:已兑换{年/季/月}卡 · Pro +{N}天。 */
export function redeemSuccessText(result: RedeemResult): string {
  const card =
    result.days_added >= 365 ? '年卡' : result.days_added >= 90 ? '季卡' : '月卡'
  return `已兑换${card} · Pro +${result.days_added} 天`
}

/** 复制本批全部码(换行分隔,方便批量发)。 */
export function joinCodes(codes: string[]): string {
  return codes.join('\n')
}
