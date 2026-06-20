/**
 * 「答题赢会员」官网首访弹窗 · 已看过标记 · B 期刀5。
 *
 * ★ 对齐项目客户端记忆约定 = cookie(不用 localStorage)· 同 color-pref.ts / ref-cookie.ts 范式:
 *   document.cookie + path=/ + max-age + SameSite=Lax。
 * 关闭后 N 天内不再弹(避免频繁打扰)· SSR 阶段视为"已看过"(不在服务端渲染弹窗)。
 */

const COOKIE = 'academy_promo_seen'
const MAX_AGE_S = 14 * 24 * 3600 // 14 天不再弹

export function hasSeenAcademyPromo(): boolean {
  if (typeof document === 'undefined') return true // SSR:不弹
  return new RegExp(`(?:^|;\\s*)${COOKIE}=1`).test(document.cookie)
}

export function markAcademyPromoSeen(): void {
  if (typeof document === 'undefined') return
  document.cookie = `${COOKIE}=1; path=/; max-age=${MAX_AGE_S}; SameSite=Lax`
}
