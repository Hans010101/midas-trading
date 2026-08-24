/**
 * 管理页展示纯逻辑(用户管理刀2)· vitest 可测。
 * 纯函数零依赖:注册方式徽标 / 最后活跃文案(7d 口径)。
 */

import type { RegisterMethod } from '@/lib/api/admin'

export const REGISTER_METHOD_LABEL: Record<RegisterMethod, string> = {
  google: 'Google',
  password: '邮箱',
  both: 'Google+邮箱',
  sms: '短信',
}

export function registerMethodLabel(method: string): string {
  return REGISTER_METHOD_LABEL[method as RegisterMethod] ?? method
}

/**
 * 最后活跃文案:null = 该用户没有未过期 session(7 天滚动 TTL 口径)。
 * 非 null → 本地化短格式(zh-CN · 到分钟)。
 */
export function lastActiveText(iso: string | null): string {
  if (iso === null) return '7 天内无活跃'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return '7 天内无活跃'
  return d.toLocaleString('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

/** 注册时间(日期粒度即可)。 */
export function createdAtText(iso: string): string {
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  return d.toLocaleDateString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  })
}
