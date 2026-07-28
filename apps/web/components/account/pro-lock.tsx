'use client'

/**
 * Pro 门控遮罩(变现强化 · 两道门)· 决策卡 / 策略清单等 Pro 内容锁定时显示。
 *
 * 按登录态区分文案(两道钩子):
 *   - 未登录 → 「登录后查看 …」+「登录 / 注册」(第一道门:注册墙)
 *   - 已登录 → 会员门槛已停用；若仍出现锁态，引导重新登录刷新会话
 *
 * 🔴 前端遮罩只是 UX;真正拦截在后端(locked=True 时后端已无真实内容 · F12 也拿不到)。
 */

import { Lock } from 'lucide-react'
import { useSession } from 'next-auth/react'
import { useRouter } from 'next/navigation'

import { cn } from '@/lib/utils'

export function ProLock({
  title = 'AI 决策分析',
  compact = false,
  className,
}: {
  title?: string
  compact?: boolean
  className?: string
}) {
  const { data: session } = useSession()
  const router = useRouter()
  const guest = !session?.accessToken

  const goto = () => router.push('/login')

  if (compact) {
    // 信号条等窄区域:单行内联(图标 + 短文案 + 行动词)
    return (
      <button
        type="button"
        onClick={goto}
        className={cn(
          'inline-flex items-center gap-1.5 text-xs text-muted-foreground/80 transition-colors hover:text-gold',
          className,
        )}
      >
        <Lock className="h-3.5 w-3.5 text-gold" />
        <span>{guest ? `登录后查看${title}` : `${title} · 请刷新登录状态`}</span>
        <span className="font-medium text-midas-red">登录</span>
      </button>
    )
  }

  return (
    <div
      className={cn(
        'flex flex-col items-center justify-center gap-3 rounded-md border border-dashed',
        'border-gold/50 bg-cream/70 px-4 py-8 text-center backdrop-blur-sm',
        className,
      )}
    >
      <Lock className="h-6 w-6 text-gold" />
      <p className="text-xs leading-relaxed text-muted-foreground">
        {guest ? `登录后查看${title}` : '登录状态已失效，请重新登录'}
      </p>
      <button
        type="button"
        onClick={goto}
        className="rounded-md bg-midas-red px-4 py-1.5 text-xs font-medium text-white transition-colors hover:bg-midas-red-deep"
      >
        {guest ? '登录 / 注册' : '重新登录'}
      </button>
    </div>
  )
}
