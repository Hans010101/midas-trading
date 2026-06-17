'use client'

/**
 * Pro 门控遮罩(变现强化 · 两道门)· 决策卡 / 策略清单等 Pro 内容锁定时显示。
 *
 * 按登录态区分文案(两道钩子):
 *   - 未登录 → 「登录后查看 …」+「登录 / 注册」(第一道门:注册墙)
 *   - 免费登录 → 「此权益仅供 Pro 会员使用」+「开通 Pro」(第二道门:付费墙)
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

  const goto = () => router.push(guest ? '/login' : '/account/membership')

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
        <span>{guest ? `登录后查看${title}` : `${title} · Pro 专享`}</span>
        <span className="font-medium text-midas-red">{guest ? '登录' : '开通 Pro'}</span>
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
        {guest ? `登录后查看${title}` : '此权益仅供 Pro 会员使用'}
      </p>
      {!guest && (
        <p className="-mt-1 text-[11px] text-muted-foreground/70">开通 Pro 解锁{title}</p>
      )}
      <button
        type="button"
        onClick={goto}
        className="rounded-md bg-midas-red px-4 py-1.5 text-xs font-medium text-white transition-colors hover:bg-midas-red-deep"
      >
        {guest ? '登录 / 注册' : '开通 Pro'}
      </button>
    </div>
  )
}
