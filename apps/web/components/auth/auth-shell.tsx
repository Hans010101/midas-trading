'use client'

/**
 * 鉴权页面共享外壳:Logo 衬线大标题 + 米白卡 + 中国红主 CTA + 合规副脚。
 * /login /register /verify-email 三个页面包在这里。
 *
 * 布局:min-h-screen 撑满背景,内容从顶部 padding 自然 flow,
 * 不用垂直居中(避免 footer 之下出现一段视觉空白)。
 */

import Link from 'next/link'
import type { ReactNode } from 'react'

interface AuthShellProps {
  title: string
  subtitle?: string
  children: ReactNode
  /** 卡片下方的 next link(如 "已有账号?登录")*/
  footer?: ReactNode
}

export function AuthShell({ title, subtitle, children, footer }: AuthShellProps) {
  return (
    <main className="min-h-screen bg-background">
      <div className="mx-auto w-full max-w-md px-6 pt-16 pb-10">
        <Link href="/" className="mb-8 block text-center">
          <h1 className="font-serif text-3xl font-bold text-foreground">
            点金 <span className="text-midas-red">Midas</span>
          </h1>
        </Link>

        <div className="rounded-lg border border-paper bg-cream p-8 shadow-sm">
          <h2 className="mb-2 font-serif text-2xl font-bold text-foreground">{title}</h2>
          {subtitle && (
            <p className="mb-6 text-sm text-muted-foreground">{subtitle}</p>
          )}
          {children}
        </div>

        {footer && <div className="mt-4 text-center text-sm">{footer}</div>}

        <p className="mt-8 text-center text-xs text-muted-foreground/70">
          模拟交易,不构成投资建议
        </p>
      </div>
    </main>
  )
}
