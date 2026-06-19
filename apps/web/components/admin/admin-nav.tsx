'use client'

/** /admin 内部导航(兑换码刀2:用户管理 / 兑换码 两 tab · 平级)。 */

import Link from 'next/link'
import { usePathname } from 'next/navigation'

const ADMIN_TABS = [
  { href: '/admin', label: '用户管理', exact: true },
  { href: '/admin/redeem-codes', label: '兑换码', exact: false },
  { href: '/admin/visit-stats', label: '访问看板', exact: false },
] as const

export function AdminNav() {
  const pathname = usePathname()
  return (
    <nav className="mb-6 flex gap-2 border-b border-paper" aria-label="管理导航">
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
