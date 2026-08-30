'use client'

/** Cloudflare 独立项目的管理员导航。兑换码能力保留但在免费期隐藏。 */

import Link from 'next/link'
import { usePathname } from 'next/navigation'

export const ADMIN_TABS = [
  { href: '/admin', label: '用户管理', exact: true },
  { href: '/admin/visit-stats', label: '访问看板', exact: false },
  { href: '/admin/academy-stats', label: '训练营统计', exact: false },
  { href: '/admin/weekly-dispatch', label: '周报发送', exact: false },
  { href: '/admin/x-tweets', label: '每日推文', exact: false },
  { href: '/admin/managed', label: '托管交易', exact: false },
  { href: '/admin/intelligent', label: '智能交易', exact: false },
  { href: '/admin/support-tickets', label: '支持工单', exact: false },
] as const

export function AdminNav() {
  const pathname = usePathname()
  return (
    <nav
      className="mb-6 flex gap-2 overflow-x-auto border-b border-paper [scrollbar-width:none] [&::-webkit-scrollbar]:hidden"
      aria-label="管理导航"
    >
      {ADMIN_TABS.map((t) => {
        const active = t.exact ? pathname === t.href : pathname?.startsWith(t.href)
        return (
          <Link
            key={t.href}
            href={t.href}
            className={
              active
                ? '-mb-px border-b-2 border-midas-red px-3 py-2 text-sm font-medium text-midas-red'
                : '-mb-px border-b-2 border-transparent px-3 py-2 text-sm text-muted-foreground transition-colors hover:text-foreground'
            }
          >
            {t.label}
          </Link>
        )
      })}
    </nav>
  )
}
