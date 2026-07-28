'use client'

/** /admin 内部导航。商业会员停用期间不展示兑换码入口。 */

import Link from 'next/link'
import { usePathname } from 'next/navigation'

const ADMIN_TABS = [
  { href: '/admin', label: '用户管理', exact: true },
  { href: '/admin/visit-stats', label: '访问看板', exact: false },
  { href: '/admin/academy-stats', label: '训练营统计', exact: false },
  // 「市场周报」(AI 生成链路 /admin/reports)入口已下掉(改用「周报发送」运营上传)·
  // 页面文件 + 后端端点保留不删,仅去导航入口(降低误删风险,未来可重启用)。
  { href: '/admin/weekly-dispatch', label: '周报发送', exact: false },
  { href: '/admin/x-tweets', label: '每日推文', exact: false },
  { href: '/admin/managed', label: '托管交易', exact: false },
  { href: '/admin/intelligent', label: '智能交易', exact: false },
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
