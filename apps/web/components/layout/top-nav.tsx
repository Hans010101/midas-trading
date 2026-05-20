'use client'

/**
 * 共享顶部导航 · Logo + 3 个页面 Tab + 用户菜单占位。
 *
 * 使用 usePathname 判断当前页高亮:
 * - /workbench    → 自选 K 线
 * - /account      → 我的账户
 * - /settings    → 设置
 */

import Link from 'next/link'
import { usePathname } from 'next/navigation'

import { cn } from '@/lib/utils'

interface NavItem {
  href: string
  label: string
  /** 匹配前缀的子路径(如 /settings/* 全部高亮设置)*/
  matchPrefix?: string
}

const NAV_ITEMS: NavItem[] = [
  { href: '/workbench', label: '自选 K 线' },
  { href: '/account', label: '我的账户' },
  { href: '/settings', label: '设置' },
]

export function TopNav() {
  const pathname = usePathname()

  return (
    <header className="h-12 shrink-0 border-b border-paper bg-background">
      <div className="flex h-full items-center justify-between px-6">
        <Link href="/workbench" className="flex items-center">
          <span className="font-serif text-lg font-bold text-foreground">
            点金 <span className="text-midas-red">Midas</span>
          </span>
        </Link>

        <nav className="flex items-center gap-1" aria-label="页面导航">
          {NAV_ITEMS.map((item) => {
            const active = item.matchPrefix
              ? pathname.startsWith(item.matchPrefix)
              : pathname === item.href
            return (
              <Link
                key={item.href}
                href={item.href}
                className={cn(
                  'rounded-md px-3 py-1 text-sm transition-colors',
                  active
                    ? 'bg-midas-red-glow text-midas-red font-medium'
                    : 'text-muted-foreground hover:bg-midas-red-glow/50 hover:text-foreground',
                )}
              >
                {item.label}
              </Link>
            )
          })}
        </nav>

        <div className="text-xs text-muted-foreground/70">用户菜单 · M0 占位</div>
      </div>
    </header>
  )
}
