'use client'

/**
 * 共享顶部导航(单行)· Logo + 市场 Tab(MarketSwitcher)+ 用户头像下拉。
 *
 * 2026-06 重构:原两行(TopNav 菜单行 + 独立 MarketSwitcher 行)整合成一行 ——
 *  - 左:Logo + MarketSwitcher(全球/A股/美股/加密/港股/自选 Tab 常驻 · 复用现成组件)
 *  - 右:用户头像(email 首字母 + 中国红圆底)→ 下拉:邮箱 + 我的账户 / 设置 / 退出登录
 *  - 去掉原「市场」入口键(Tab 已常驻)+ 内联邮箱/退出登录(收进下拉)
 *
 * ★ 纯 UI/布局:MarketSwitcher 点击仍走其原有路由/store 逻辑(只挪位置,行为不变)。
 */

import Image from 'next/image'
import Link from 'next/link'
import { signOut, useSession } from 'next-auth/react'

import { MarketSwitcher } from '@/components/layout/market-switcher'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'

export function TopNav() {
  const { data: session, status } = useSession()
  const email = session?.user?.email ?? ''
  const initial = email.charAt(0).toUpperCase() || '?'

  return (
    <header className="h-12 shrink-0 border-b border-paper bg-background">
      <div className="flex h-full items-center justify-between px-6">
        {/* 左:Logo + 市场 Tab(常驻 · gap 留间距)· 移动刀B:min-w-0 允许切换条收缩进横滚 */}
        <div className="flex min-w-0 items-center gap-5">
          <Link href="/" className="flex shrink-0 items-center gap-2">
            <Image src="/brand/seal.png" alt="Midas 印章" width={24} height={24} priority />
            <span className="font-serif text-lg font-bold text-midas-red">Midas</span>
          </Link>
          <MarketSwitcher />
        </div>

        {/* 右:用户头像下拉(登录态)/ 登录入口(未登录)/ loading 占位 */}
        <div className="flex items-center">
          {status === 'authenticated' && session?.user ? (
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <button
                  type="button"
                  aria-label="用户菜单"
                  className="flex h-8 w-8 items-center justify-center rounded-full bg-midas-red text-sm font-bold text-white transition-opacity hover:opacity-90 focus:outline-none focus-visible:ring-2 focus-visible:ring-midas-red/40"
                >
                  {initial}
                </button>
              </DropdownMenuTrigger>
              {/* 右上角弹出 → 全菜单右对齐 + 收窄(Hans 真机反馈 · 刀2 补充) */}
              <DropdownMenuContent align="end" className="w-40">
                <DropdownMenuLabel
                  className="truncate text-right text-xs font-normal text-muted-foreground"
                  title={email}
                >
                  {email}
                </DropdownMenuLabel>
                <DropdownMenuSeparator />
                {/* 用户中心四模块直达(重组刀1)· 自选已删(顶部导航已有入口,菜单内重复) */}
                <DropdownMenuItem asChild className="justify-end">
                  <Link href="/account">资产总览</Link>
                </DropdownMenuItem>
                <DropdownMenuItem asChild className="justify-end">
                  <Link href="/account/positions">持仓与订单</Link>
                </DropdownMenuItem>
                <DropdownMenuItem asChild className="justify-end">
                  <Link href="/account/alerts">通知与提醒</Link>
                </DropdownMenuItem>
                <DropdownMenuItem asChild className="justify-end">
                  <Link href="/account/profile">账号与偏好</Link>
                </DropdownMenuItem>
                <DropdownMenuSeparator />
                <DropdownMenuItem
                  onClick={() => {
                    // signOut 触发 NextAuth 清 cookie + auth.ts events.signOut(回调后端 revoke DB session)
                    void signOut({ callbackUrl: '/' })
                  }}
                  className="justify-end text-midas-red focus:text-midas-red"
                >
                  退出登录
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
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
