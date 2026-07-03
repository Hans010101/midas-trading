'use client'

/**
 * 用户中心四模块导航(重组刀1)· 一个组件按断点两种渲染:
 *   lg+   → 左侧栏(竖排 · 当前项中国红高亮 + 左边线)
 *   lg 以下 → 顶部水平 scrollable tab(照 lab-nav framed-segment 范式)
 */

import Link from 'next/link'
import { usePathname } from 'next/navigation'

import { ACCOUNT_NAV_ITEMS, isActiveNavItem } from '@/lib/account-nav'
import { cn } from '@/lib/utils'

export function AccountNav() {
  const pathname = usePathname()

  return (
    <>
      {/* lg+ 左侧栏 */}
      <nav className="hidden w-44 shrink-0 lg:block" aria-label="用户中心导航">
        <ul className="space-y-1">
          {ACCOUNT_NAV_ITEMS.map((item) => {
            const active = isActiveNavItem(pathname, item)
            return (
              <li key={item.href}>
                <Link
                  href={item.href}
                  className={cn(
                    'block rounded-md border-l-2 px-3 py-2 text-sm transition-colors',
                    active
                      ? 'border-midas-red bg-midas-red-glow font-medium text-midas-red'
                      : 'border-transparent text-muted-foreground hover:bg-cream hover:text-foreground',
                  )}
                >
                  {item.label}
                </Link>
              </li>
            )
          })}
        </ul>
      </nav>

      {/* lg 以下 顶部水平 tab(framed-segment · 窄屏可横滚) */}
      <div className="mb-6 overflow-x-auto lg:hidden">
        <div className="flex w-max min-w-full overflow-hidden rounded-md border border-paper text-sm">
          {ACCOUNT_NAV_ITEMS.map((item) => {
            const active = isActiveNavItem(pathname, item)
            return (
              <Link
                key={item.href}
                href={item.href}
                className={cn(
                  'whitespace-nowrap px-4 py-1.5 transition-colors',
                  active
                    ? 'bg-midas-red text-white'
                    : 'text-muted-foreground hover:bg-midas-red-glow/50',
                )}
              >
                {item.label}
              </Link>
            )
          })}
        </div>
      </div>
    </>
  )
}
