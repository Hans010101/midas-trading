'use client'

/**
 * 加入自选 / 取消自选 按钮(0023 阶段③ · 3.6)· 三个详情页共用(cn/us/crypto)。
 *
 * 复用 0007 既有 watchlist 存储/接口(user_id + symbol + market · 已是用户级跨市场)·
 * 零后端改动、零迁移。
 *  - 未登录 → 引导登录(/login)
 *  - 已登录 + 已在自选 → 帝王金「已自选」· 点击取消(乐观更新)
 *  - 已登录 + 未在自选 → 描边「加自选」· 点击加入
 *
 * 红线:只读行情 · 全程虚拟资金。
 */

import Link from 'next/link'
import { Star } from 'lucide-react'
import { useMemo } from 'react'
import { toast } from 'sonner'

import { useSession } from 'next-auth/react'
import {
  useAddToWatchlist,
  useDeleteFromWatchlist,
  useWatchlist,
} from '@/hooks/use-watchlist'
import { WatchlistApiError } from '@/lib/api/watchlist'
import { cn } from '@/lib/utils'
import type { Market } from '@midas/shared'

interface Props {
  symbol: string
  market: Market
}

export function WatchlistToggleButton({ symbol, market }: Props) {
  const { status } = useSession()
  const { data: items } = useWatchlist()
  const add = useAddToWatchlist()
  const del = useDeleteFromWatchlist()

  const existing = useMemo(
    () => (items ?? []).find((it) => it.symbol === symbol && it.market === market),
    [items, symbol, market],
  )
  const inList = Boolean(existing)
  const pending = add.isPending || del.isPending

  if (status === 'loading') {
    return (
      <button
        type="button"
        disabled
        className="inline-flex items-center gap-1 rounded-md border border-paper px-2.5 py-1 text-xs text-muted-foreground/60"
      >
        <Star className="h-3.5 w-3.5" />
        加自选
      </button>
    )
  }

  if (status === 'unauthenticated') {
    return (
      <Link
        href="/login"
        title="登录后可加入自选"
        className="inline-flex items-center gap-1 rounded-md border border-paper px-2.5 py-1 text-xs text-muted-foreground transition-colors hover:border-gold/60 hover:text-gold"
      >
        <Star className="h-3.5 w-3.5" />
        加自选
      </Link>
    )
  }

  async function toggle() {
    try {
      if (existing) {
        await del.mutateAsync(existing.id)
        toast.success(`已取消自选 ${symbol}`)
      } else {
        await add.mutateAsync({ symbol, market })
        toast.success(`已加入自选 ${symbol}`, { className: 'midas-toast-success' })
      }
    } catch (e) {
      toast.error(e instanceof WatchlistApiError ? e.detail : '操作失败,请稍后重试')
    }
  }

  return (
    <button
      type="button"
      onClick={() => void toggle()}
      disabled={pending}
      aria-pressed={inList}
      className={cn(
        'inline-flex items-center gap-1 rounded-md border px-2.5 py-1 text-xs transition-colors',
        pending && 'opacity-60',
        inList
          ? 'border-gold bg-gold/10 text-gold'
          : 'border-paper text-muted-foreground hover:border-gold/60 hover:text-gold',
      )}
    >
      <Star className={cn('h-3.5 w-3.5', inList && 'fill-current')} />
      {inList ? '已自选' : '加自选'}
    </button>
  )
}
