'use client'

/**
 * 全局命令面板(Cmd/Ctrl+K)· 泛化自 workbench/symbol-search-dialog。
 *
 * 由产品顶栏 TopNav 渲染 → 登录后所有产品页全局生效;landing 用自己的 nav,天然排除(方案 C)。
 *
 * 能力:
 *  A. 品种搜索:useSymbolSearch → /api/v1/market/symbols 四市场模糊匹配(★含 hk)· 按市场分组。
 *     · 选中(Enter/点击)→ 跳详情页 *-preview?symbol=(零 [id] · crypto 无 name · cn/us/hk 带 name);
 *     · 次级「加自选」(右侧 + 按钮 · stopPropagation 不触发跳转)→ POST /watchlist(复用 useAddToWatchlist)。
 *  B. 功能页快速跳转(静态组 · ★不含训练营,系统性学习不适合快速跳)。
 *  C. 空闲态(无输入)→ 显示用户自选(GET /watchlist + 涨跌幅)· 选中跳详情;未登录/空仅显功能页。
 *
 * 搜索 / 自选端点全现成 → 纯前端零后端改动。CommandDialog(Radix Dialog · 焦点陷阱 / ESC / a11y 内置)。
 */

import { Plus } from 'lucide-react'
import { useRouter } from 'next/navigation'
import { useState } from 'react'

import {
  CommandDialog,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
  CommandSeparator,
} from '@/components/ui/command'
import { DialogDescription, DialogTitle } from '@/components/ui/dialog'
import { useRequireAuth } from '@/hooks/use-require-auth'
import { useSymbolSearch } from '@/hooks/use-symbol-search'
import { useAddToWatchlist, useWatchlist } from '@/hooks/use-watchlist'
import { useWatchlistQuotes } from '@/hooks/use-watchlist-quotes'
import { WatchlistApiError } from '@/lib/api/watchlist'
import { FUNC_PAGES, MARKET_ORDER, symbolHref } from '@/lib/command-palette-nav'
import { MARKET_LABEL, formatPct } from '@/lib/format-money'
import { cn } from '@/lib/utils'
import type { Market, SymbolMeta } from '@midas/shared'

function chipClass(m: Market): string {
  if (m === 'cn') return 'text-midas-red border border-midas-red/30 bg-midas-red-glow/40'
  if (m === 'us') return 'text-foreground border border-paper bg-paper/60'
  if (m === 'hk') return 'text-foreground/70 border border-foreground/15 bg-foreground/[0.04]'
  return 'text-gold border border-gold/30 bg-gold/10' // crypto
}

interface Props {
  open: boolean
  onOpenChange: (open: boolean) => void
}

export function CommandPalette({ open, onOpenChange }: Props) {
  const router = useRouter()
  const [query, setQuery] = useState('')
  const trimmedQ = query.trim()
  const showIdle = trimmedQ.length === 0

  const { data: results = [], isFetching } = useSymbolSearch(query)
  const { data: watchItems = [] } = useWatchlist()
  // 仅空闲态才拉自选行情(避免搜索时多发无用 kline 请求)
  const quotes = useWatchlistQuotes(showIdle ? watchItems : [])
  const addMutation = useAddToWatchlist()
  const { requireAuth } = useRequireAuth()
  const [feedback, setFeedback] = useState<string | null>(null)

  const grouped = groupByMarket(results)

  function go(href: string) {
    setQuery('')
    setFeedback(null)
    onOpenChange(false)
    router.push(href)
  }

  async function addWatch(item: { symbol: string; market: Market }) {
    if (!requireAuth('加自选股')) {
      onOpenChange(false)
      return
    }
    setFeedback(null)
    try {
      await addMutation.mutateAsync({ symbol: item.symbol, market: item.market })
      setFeedback(`✓ ${item.symbol} 已加入自选`)
    } catch (e) {
      if (e instanceof WatchlistApiError) {
        setFeedback(e.status === 409 ? `${item.symbol} 已在自选列表` : e.detail)
      } else {
        setFeedback('加自选失败,请重试')
      }
    }
  }

  function handleOpenChange(next: boolean) {
    if (!next) {
      setQuery('')
      setFeedback(null)
    }
    onOpenChange(next)
  }

  return (
    <CommandDialog open={open} onOpenChange={handleOpenChange}>
      {/* a11y:Radix Dialog 要求 Title/Description(屏幕阅读器)· sr-only 不影响视觉 */}
      <DialogTitle className="sr-only">命令面板 · 搜索品种或跳转功能页</DialogTitle>
      <DialogDescription className="sr-only">
        输入代码 / 中文名搜四市场标的(选中跳详情),或选功能页快速跳转
      </DialogDescription>
      <CommandInput
        placeholder="搜品种(600519 / NVDA / BTC / 腾讯)· 或跳功能页…"
        value={query}
        onValueChange={(v) => {
          setQuery(v)
          setFeedback(null)
        }}
      />
      <CommandList>
        {feedback && (
          <div className="border-b border-paper px-3 py-2 text-xs text-midas-red">{feedback}</div>
        )}

        {isFetching && !showIdle && (
          <div className="px-3 py-3 text-center text-xs text-muted-foreground/60">搜索中…</div>
        )}
        {/* cmdk 自管可见性:仅 0 命中时显示;!isFetching 渲染避免搜索中闪现 */}
        {!isFetching && <CommandEmpty>没有匹配,试试代码 / 中文名</CommandEmpty>}

        {/* 空闲态:我的自选 */}
        {showIdle && watchItems.length > 0 && (
          <CommandGroup heading="我的自选">
            {watchItems.map((it) => {
              const q = quotes.find((x) => x.symbol === it.symbol)
              return (
                <CommandItem
                  key={`w-${it.id}`}
                  value={`zixuan ${it.symbol} ${it.market}`}
                  onSelect={() => go(symbolHref({ symbol: it.symbol, market: it.market }))}
                  className="flex items-center justify-between"
                >
                  <span className="flex min-w-0 items-center gap-3">
                    <span className="font-mono text-xs text-foreground">{it.symbol}</span>
                    <span
                      className={cn(
                        'shrink-0 rounded px-1.5 py-0.5 text-[10px] leading-tight',
                        chipClass(it.market),
                      )}
                    >
                      {MARKET_LABEL[it.market]}
                    </span>
                  </span>
                  {q?.changePct != null ? (
                    <span
                      className={cn('font-mono text-xs', q.changePct >= 0 ? 'text-up' : 'text-down')}
                    >
                      {formatPct(q.changePct)}
                    </span>
                  ) : (
                    <span className="text-xs text-muted-foreground/40">—</span>
                  )}
                </CommandItem>
              )
            })}
          </CommandGroup>
        )}

        {/* 品种搜索结果(四市场分组 · 含 hk)*/}
        {!showIdle &&
          MARKET_ORDER.map((m) => {
            const list = grouped[m]
            if (!list?.length) return null
            return (
              <CommandGroup key={m} heading={MARKET_LABEL[m]}>
                {list.map((item) => (
                  <CommandItem
                    key={`${m}-${item.symbol}`}
                    value={`${item.symbol} ${item.name} ${item.name_en}`}
                    onSelect={() => go(symbolHref(item))}
                    className="flex items-center justify-between gap-2"
                  >
                    <span className="flex min-w-0 items-center gap-3">
                      <span className="font-mono text-xs text-foreground">{item.symbol}</span>
                      <span className="truncate text-sm text-foreground">{item.name}</span>
                    </span>
                    <span className="flex shrink-0 items-center gap-2">
                      <span
                        className={cn(
                          'rounded px-1.5 py-0.5 text-[10px] leading-tight',
                          chipClass(m),
                        )}
                      >
                        {MARKET_LABEL[m]}
                      </span>
                      {/* 次级:加自选(stopPropagation · 不触发 onSelect 跳详情)*/}
                      <button
                        type="button"
                        aria-label={`加自选 ${item.symbol}`}
                        onClick={(e) => {
                          e.stopPropagation()
                          void addWatch(item)
                        }}
                        className="rounded p-1 text-muted-foreground transition-colors hover:bg-midas-red-glow hover:text-midas-red"
                      >
                        <Plus className="h-3.5 w-3.5" />
                      </button>
                    </span>
                  </CommandItem>
                ))}
              </CommandGroup>
            )
          })}

        {/* 功能页快速跳转(常显 · cmdk 按输入过滤 · 搜「会员」「终端」可命中)*/}
        {showIdle && watchItems.length > 0 && <CommandSeparator />}
        <CommandGroup heading="快速跳转">
          {FUNC_PAGES.map((p) => (
            <CommandItem
              key={p.href}
              value={`${p.label} ${p.hint}`}
              onSelect={() => go(p.href)}
              className="flex items-center justify-between"
            >
              <span className="text-sm text-foreground">{p.label}</span>
              <span className="text-xs text-muted-foreground/60">{p.hint}</span>
            </CommandItem>
          ))}
        </CommandGroup>
      </CommandList>
    </CommandDialog>
  )
}

function groupByMarket(results: SymbolMeta[]): Record<Market, SymbolMeta[]> {
  return results.reduce<Record<Market, SymbolMeta[]>>(
    (acc, r) => {
      acc[r.market].push(r)
      return acc
    },
    { cn: [], us: [], crypto: [], hk: [] },
  )
}
