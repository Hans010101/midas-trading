/**
 * 额度展示纯逻辑(会员刀2)· vitest 可测。
 *
 * 🔴 红线:额度展示如实 —— 剩几次是几次,不夸大不隐瞒(直接 limit-used,无修饰)。
 */

import type { QuotaItem, QuotaMe } from '@/lib/api/quota'

export function quotaItemFor(quota: QuotaMe | undefined, feature: string): QuotaItem | null {
  return quota?.items.find((it) => it.feature === feature) ?? null
}

export function quotaRemaining(item: QuotaItem): number {
  return Math.max(0, item.limit - item.used)
}

export function isExhausted(item: QuotaItem): boolean {
  return item.used >= item.limit
}

/** 按钮旁小字:「今日剩 N/20 次」。 */
export function quotaHintText(item: QuotaItem): string {
  return `今日剩 ${quotaRemaining(item)}/${item.limit} 次`
}

export const EXHAUSTED_TEXT = '今日额度已用完,明日 0 点重置(UTC+8)'
export const RESET_NOTE = '每日 0 点重置(UTC+8)'

export interface QuotaExceededDetail {
  error: 'quota_exceeded'
  feature: string
  plan: string
  limit: number
  used: number
  reset_at: string
}

/** 429 detail(后端六字段结构化 dict)解析 · 形状不符返回 null(走通用错误文案)。 */
export function parseQuotaDetail(detail: unknown): QuotaExceededDetail | null {
  if (typeof detail !== 'object' || detail === null) return null
  const d = detail as Record<string, unknown>
  if (d.error !== 'quota_exceeded') return null
  if (typeof d.limit !== 'number' || typeof d.used !== 'number') return null
  return d as unknown as QuotaExceededDetail
}

/** 429 的用户文案(detail 解析成功时)。 */
export function quotaErrorMessage(detail: QuotaExceededDetail): string {
  return `今日额度已用完(${detail.used}/${detail.limit}),明日 0 点重置(UTC+8)`
}

export const PLAN_LABEL: Record<string, string> = {
  free: '免费版',
  pro: '进阶版 Pro',
}

export function planLabel(plan: string): string {
  return PLAN_LABEL[plan] ?? plan
}
