'use client'

/**
 * 自选汇总页(0023 阶段③ · 3.6)· 跨市场(A股/美股/加密)混合展示。
 *
 * 复用 0007 watchlist 接口(useWatchlist · 已是用户级跨市场)+ 0007 报价 hook
 * (useWatchlistQuotes · 每标的 /market/kline 末两根算价 + 涨跌幅 · 30s 轮询)。
 * 用 0022 阶段② 共用组件(DataTable / EmptyState / LoadingNote)· 视觉跟三市场首页统一。
 *
 * 每行:市场徽章 + 代码 + 最新价(原币种)+ 涨跌幅 · 点行 → 新标签开对应详情页 · 行尾可取消自选。
 * 红线:只读行情。
 */

import { Star, X } from 'lucide-react'
import Link from 'next/link'
import { toast } from 'sonner'

import { useSession } from 'next-auth/react'
import { DataTable, TCell, TH, THead, TRow } from '@/components/ui/data-table'
import { EmptyState, LoadingNote } from '@/components/ui/state'
import { useDeleteFromWatchlist, useWatchlist } from '@/hooks/use-watchlist'
import { useWatchlistQuotes } from '@/hooks/use-watchlist-quotes'
import { WatchlistApiError } from '@/lib/api/watchlist'
import { currencyOf, formatMoney } from '@/lib/format-money'
import { cn } from '@/lib/utils'
import type { Market } from '@midas/shared'

const MARKET_LABEL: Record<Market, string> = { cn: 'A 股', us: '美股', crypto: '加密', hk: '港股' }
const MARKET_BADGE: Record<Market, string> = {
  cn: 'border-midas-red/40 text-midas-red',
  us: 'border-gold/50 text-gold',
  crypto: 'border-paper text-muted-foreground',
  hk: 'border-paper text-muted-foreground',
}
const PREVIEW_PATH: Record<Market, string> = {
  cn: '/cn-preview',
  us: '/us-preview',
  crypto: '/crypto-preview',
  hk: '/hk-market', // 港股暂无个股详情页 · 指向占位页(数据 P1-3 后再做 hk-preview)
}

function openDetail(market: Market, symbol: string) {
  window.open(
    `${PREVIEW_PATH[market]}?symbol=${encodeURIComponent(symbol)}`,
    '_blank',
    'noopener,noreferrer',
  )
}

function fmtPct(n: number): string {
  return `${n >= 0 ? '+' : ''}${n.toFixed(2)}%`
}

export function WatchlistOverview() {
  const { status } = useSession()
  const { data: items = [], isLoading, isError } = useWatchlist()
  const quotes = useWatchlistQuotes(items)
  const del = useDeleteFromWatchlist()

  if (status === 'unauthenticated') {
    return (
      <div className="mx-auto max-w-md rounded-lg border border-dashed border-paper bg-cream p-6 text-center">
        <Star className="mx-auto mb-2 h-6 w-6 text-gold" />
        <p className="mb-1 text-sm font-medium text-foreground">登录后查看自选</p>
        <p className="mb-4 text-xs leading-relaxed text-muted-foreground/80">
          登录即可跨 A股 / 美股 / 加密 收藏关注的标的,汇总到这一个界面。
        </p>
        <Link
          href="/login"
          className="inline-flex items-center rounded-md border border-midas-red px-3 py-1 text-xs text-midas-red transition-colors hover:bg-midas-red-glow"
        >
          去登录
        </Link>
      </div>
    )
  }

  async function remove(id: number, symbol: string) {
    try {
      await del.mutateAsync(id)
      toast.success(`已取消自选 ${symbol}`)
    } catch (e) {
      toast.error(e instanceof WatchlistApiError ? e.detail : '操作失败')
    }
  }

  return (
    <section>
      <div className="mb-3 flex items-center justify-between">
        <h2 className="font-serif text-sm font-bold text-foreground">我的自选 · 跨市场</h2>
        {items.length > 0 && (
          <span className="text-xs text-muted-foreground/70">共 {items.length} 个标的</span>
        )}
      </div>

      {(isLoading || status === 'loading') && <LoadingNote className="py-10" />}
      {isError && <EmptyState title="暂时无法读取自选" hint="后端不可达 · 稍后自动重试" />}
      {!isLoading && !isError && items.length === 0 && (
        <EmptyState
          title="自选还是空的"
          hint="去 A股 / 美股 / 加密 任一详情页,点「加自选」收藏关注的标的"
        />
      )}

      {items.length > 0 && (
        <>
          <DataTable minWidth="640px">
            <THead>
              <TH align="center">#</TH>
              <TH>市场</TH>
              <TH>代码</TH>
              <TH align="right">最新价</TH>
              <TH align="right">涨跌幅</TH>
              <TH align="center">操作</TH>
            </THead>
            <tbody>
              {items.map((it, i) => {
                const q = quotes[i]
                const market = it.market
                return (
                  <TRow
                    key={it.id}
                    onClick={() => openDetail(market, it.symbol)}
                    className="cursor-pointer transition-colors hover:bg-midas-red-glow/30"
                    title="点击查看详情"
                  >
                    <TCell align="center" mono className="text-xs text-muted-foreground/70">
                      {i + 1}
                    </TCell>
                    <TCell>
                      <span
                        className={cn(
                          'inline-block rounded border px-1.5 py-0.5 text-[10px]',
                          MARKET_BADGE[market],
                        )}
                      >
                        {MARKET_LABEL[market]}
                      </span>
                    </TCell>
                    <TCell mono className="font-medium text-foreground">
                      {it.symbol}
                    </TCell>
                    <TCell align="right" mono>
                      {q?.isLoading
                        ? '…'
                        : q?.close != null
                          ? formatMoney(q.close, currencyOf(market))
                          : '—'}
                    </TCell>
                    <TCell
                      align="right"
                      mono
                      className={
                        q?.changePct != null
                          ? q.changePct >= 0
                            ? 'text-up'
                            : 'text-down'
                          : 'text-muted-foreground/60'
                      }
                    >
                      {q?.changePct != null ? fmtPct(q.changePct) : '—'}
                    </TCell>
                    <TCell align="center">
                      <button
                        type="button"
                        title="取消自选"
                        onClick={(e) => {
                          e.stopPropagation()
                          void remove(it.id, it.symbol)
                        }}
                        className="inline-flex items-center rounded p-1 text-muted-foreground/60 transition-colors hover:bg-midas-red-glow hover:text-midas-red"
                      >
                        <X className="h-3.5 w-3.5" />
                      </button>
                    </TCell>
                  </TRow>
                )
              })}
            </tbody>
          </DataTable>
          <p className="mt-2 text-[11px] text-muted-foreground/60">
            最新价为各标的最近日 K 收盘(原币种)· 30 秒刷新 · 点行进对应详情页
          </p>
        </>
      )}
    </section>
  )
}
