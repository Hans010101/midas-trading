/**
 * 用户中心四模块导航(重组刀1)· 纯配置 + 高亮纯函数(vitest 可测)。
 *
 * /account 精确匹配(防子路由误亮);子模块前缀匹配。
 */

export interface AccountNavItem {
  href: string
  label: string
  exact?: boolean
}

export const ACCOUNT_NAV_ITEMS: readonly AccountNavItem[] = [
  { href: '/account', label: '资产总览', exact: true },
  { href: '/account/positions', label: '持仓与订单' },
  { href: '/account/alerts', label: '通知与提醒' },
  { href: '/account/profile', label: '账号与偏好' },
  { href: '/account/invite', label: '邀请有礼' }, // Phase 1.5 刀B
] as const

export function isActiveNavItem(pathname: string | null, item: AccountNavItem): boolean {
  if (!pathname) return false
  return item.exact ? pathname === item.href : pathname.startsWith(item.href)
}

// ── 模块② 持仓与订单 · 页内 tab(重组刀3)──────────────────────────────────

export const POSITIONS_TABS = [
  { key: 'positions', label: '当前持仓' },
  { key: 'history', label: '历史持仓' },
  { key: 'orders', label: '订单流水' },
  { key: 'conditional', label: '条件单' },
] as const

export type PositionsTabKey = (typeof POSITIONS_TABS)[number]['key']

/** URL ?tab= 归一(非法/缺省 → 'positions')· 刷新/分享不丢 tab。 */
export function normalizePositionsTab(param: string | null): PositionsTabKey {
  const valid = POSITIONS_TABS.some((t) => t.key === param)
  return valid ? (param as PositionsTabKey) : 'positions'
}
