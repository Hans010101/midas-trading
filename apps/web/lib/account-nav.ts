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
] as const

export function isActiveNavItem(pathname: string | null, item: AccountNavItem): boolean {
  if (!pathname) return false
  return item.exact ? pathname === item.href : pathname.startsWith(item.href)
}
