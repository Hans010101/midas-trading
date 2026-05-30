'use client'

/**
 * 共享顶部导航 · Logo + 3 个页面 Tab + 用户菜单占位。
 *
 * 使用 usePathname 判断当前页高亮:
 * - /cn-market /us-market /crypto-market → 市场(产品主入口 · 0023 阶段③ 导航收口)
 * - /account  → 我的账户
 * - /settings → 设置
 *
 * 0023 阶段③:市场首页 = 产品主入口;工作台(/workbench)入口已从主导航下线
 * (代码保留 · 3.4 新建 A股/美股详情页时复用其 K线/缠论/AI 组件)。
 */

import Image from 'next/image'
import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { signOut, useSession } from 'next-auth/react'

import { cn } from '@/lib/utils'

interface NavItem {
  href: string
  label: string
  /** 匹配前缀的子路径(如 /settings/* 全部高亮设置)*/
  matchPrefix?: string
}

// 市场主入口路径(全球概览默认 + 三市场首页 · ADR 0035 起全球概览为默认落地页)
const MARKET_HOME_PATHS = ['/global', '/cn-market', '/us-market', '/crypto-market'] as const

const NAV_ITEMS: NavItem[] = [
  { href: '/account', label: '我的账户' },
  { href: '/settings', label: '设置', matchPrefix: '/settings' },
]

export function TopNav() {
  const pathname = usePathname()
  const { data: session, status } = useSession()

  // "市场" 进当前所在市场页(产品主入口),不在任一市场页时默认全球概览(ADR 0035)。
  const marketHref = MARKET_HOME_PATHS.find((p) => pathname?.startsWith(p)) ?? '/global'
  const onMarketHome = MARKET_HOME_PATHS.some((p) => pathname?.startsWith(p))

  return (
    <header className="h-12 shrink-0 border-b border-paper bg-background">
      <div className="flex h-full items-center justify-between px-6">
        {/* Logo 点击回官网首页 /(终端 ⇄ 官网闭环 · 0023 阶段③ 微调) */}
        <Link href="/" className="flex items-center gap-2">
          <Image src="/brand/seal.png" alt="Midas 印章" width={24} height={24} priority />
          <span className="font-serif text-lg font-bold text-midas-red">
            Midas
          </span>
        </Link>

        <nav className="flex items-center gap-1" aria-label="页面导航">
          <Link
            href={marketHref}
            className={cn(
              'rounded-md px-3 py-1 text-sm transition-colors',
              onMarketHome
                ? 'bg-midas-red-glow text-midas-red font-medium'
                : 'text-muted-foreground hover:bg-midas-red-glow/50 hover:text-foreground',
            )}
          >
            市场
          </Link>
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

        {/* 用户菜单 · 登录态显示邮箱 + 退出登录 · 未登录显示登录入口 */}
        <div className="flex items-center gap-3">
          {status === 'authenticated' && session?.user ? (
            <>
              <span
                className="hidden max-w-[180px] truncate text-xs text-muted-foreground sm:inline"
                title={session.user.email ?? ''}
              >
                {session.user.email}
              </span>
              <button
                type="button"
                onClick={() => {
                  // signOut 触发 NextAuth 清 cookie + auth.ts events.signOut
                  // 回调后端 /api/v1/auth/logout revoke DB session · callbackUrl 回首页
                  void signOut({ callbackUrl: '/' })
                }}
                className="rounded-md border border-paper px-3 py-1 text-sm text-muted-foreground transition-colors hover:border-midas-red hover:text-midas-red"
              >
                退出登录
              </button>
            </>
          ) : status === 'unauthenticated' ? (
            <Link
              href="/login"
              className="rounded-md bg-midas-red px-3 py-1 text-sm text-white transition-colors hover:bg-midas-red/90"
            >
              登录
            </Link>
          ) : (
            // loading · 占位避免布局跳动
            <span className="text-xs text-muted-foreground/50">…</span>
          )}
        </div>
      </div>
    </header>
  )
}
