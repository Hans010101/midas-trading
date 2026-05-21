'use client'

/**
 * useRequireAuth · M1 第三波(2026-05-21 · /workbench 改匿名)。
 *
 * 用法:
 *   const { requireAuth } = useRequireAuth()
 *   const onClickBuy = () => {
 *     if (!requireAuth('下单')) return     // 未登录 · 已 toast + redirect login
 *     // 已登录 · 跑下单逻辑
 *   }
 *
 * 行为:
 * - 未登录:toast 提示「请先登录后操作」+ 0.6s 后跳 /login?next=<当前页>
 * - 已登录:直接 return true · 调用方继续
 *
 * 适用场景(产品负责人 2026-05-21 指令的 4 个):
 * - 下单(Buy / Sell)
 * - 加自选股
 * - 设置虚拟资金
 * - 保存绘图(M2+ · 当前绘图是 session 内不持久化)
 */

import { useSession } from 'next-auth/react'
import { useRouter } from 'next/navigation'
import { useCallback } from 'react'
import { toast } from 'sonner'

export function useRequireAuth() {
  const { status } = useSession()
  const router = useRouter()

  const requireAuth = useCallback(
    (actionLabel = '此操作'): boolean => {
      if (status === 'authenticated') return true
      // pending(NextAuth 加载中)· unauthenticated → 引导登录
      // 用 window.location 拿当前路径(避免 useSearchParams 触发
      // Next 15 静态导出 bailout · /workbench prerender 时 toast/router 用不到)
      const next =
        typeof window !== 'undefined'
          ? window.location.pathname + window.location.search
          : '/workbench'
      toast.info(`请先登录后${actionLabel}`, {
        description: '0.6 秒后跳转登录页',
        duration: 1200,
      })
      window.setTimeout(() => {
        router.push(`/login?next=${encodeURIComponent(next)}`)
      }, 600)
      return false
    },
    [status, router],
  )

  return { requireAuth, isAuthenticated: status === 'authenticated' }
}
