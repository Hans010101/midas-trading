'use client'

/**
 * Cmd+K 搜索弹窗:输入标的关键词 → 按 market 分组展示 → 选中后调
 * POST /api/v1/watchlist 加入自选。
 *
 * 设计参考 0007 § 4 + shadcn `command` 组件包装 cmdk。
 */

import { useState } from 'react'

import {
  CommandDialog,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from '@/components/ui/command'
import { useSymbolSearch } from '@/hooks/use-symbol-search'
import { useAddToWatchlist } from '@/hooks/use-watchlist'
import { WatchlistApiError } from '@/lib/api/watchlist'
import { cn } from '@/lib/utils'
import type { Market, SymbolMeta } from '@midas/shared'

const MARKET_LABEL: Record<Market, string> = {
  cn: 'A 股',
  us: '美股',
  crypto: '加密',
}

const MARKET_ORDER: Market[] = ['crypto', 'us', 'cn']

function chipClass(m: Market): string {
  if (m === 'cn') return 'text-midas-red border border-midas-red/30 bg-midas-red-glow/40'
  if (m === 'us') return 'text-foreground border border-paper bg-paper/60'
  return 'text-gold border border-gold/30 bg-gold/10'
}

interface Props {
  open: boolean
  onOpenChange: (open: boolean) => void
}

export function SymbolSearchDialog({ open, onOpenChange }: Props) {
  const [query, setQuery] = useState('')
  const { data: results = [], isFetching } = useSymbolSearch(query)
  const addMutation = useAddToWatchlist()
  const [errorMsg, setErrorMsg] = useState<string | null>(null)

  const grouped = groupByMarket(results)
  const trimmedQ = query.trim()

  async function handleSelect(item: SymbolMeta) {
    setErrorMsg(null)
    try {
      await addMutation.mutateAsync({ symbol: item.symbol, market: item.market })
      // 成功 → 关弹窗 + 清空输入
      onOpenChange(false)
      setQuery('')
    } catch (e) {
      if (e instanceof WatchlistApiError && e.status === 409) {
        setErrorMsg(`${item.symbol} 已在自选列表`)
      } else {
        setErrorMsg('添加失败,请重试')
      }
    }
  }

  function handleOpenChange(next: boolean) {
    if (!next) {
      setQuery('')
      setErrorMsg(null)
    }
    onOpenChange(next)
  }

  return (
    <CommandDialog open={open} onOpenChange={handleOpenChange}>
      <CommandInput
        placeholder="搜索 600519 / NVDA / BTC..."
        value={query}
        onValueChange={(v) => {
          setQuery(v)
          setErrorMsg(null)
        }}
      />
      <CommandList>
        {errorMsg && (
          <div className="border-b border-paper px-3 py-2 text-xs text-midas-red">
            {errorMsg}
          </div>
        )}
        {trimmedQ.length === 0 && (
          <div className="px-3 py-4 text-center text-xs text-muted-foreground/70">
            输入关键词搜索三市场标的
          </div>
        )}
        {trimmedQ.length >= 1 && !isFetching && results.length === 0 && (
          <CommandEmpty>没有匹配标的</CommandEmpty>
        )}
        {MARKET_ORDER.map((m) => {
          const list = grouped[m]
          if (!list?.length) return null
          return (
            <CommandGroup key={m} heading={MARKET_LABEL[m]}>
              {list.map((item) => (
                <CommandItem
                  key={`${m}-${item.symbol}`}
                  value={`${item.symbol} ${item.name} ${item.name_en}`}
                  onSelect={() => {
                    void handleSelect(item)
                  }}
                  className="flex items-center justify-between"
                >
                  <span className="flex min-w-0 items-center gap-3">
                    <span className="font-mono text-xs text-foreground">{item.symbol}</span>
                    <span className="truncate text-sm text-foreground">{item.name}</span>
                  </span>
                  <span
                    className={cn(
                      'shrink-0 rounded px-1.5 py-0.5 text-[10px] leading-tight',
                      chipClass(m),
                    )}
                  >
                    {MARKET_LABEL[m]}
                  </span>
                </CommandItem>
              ))}
            </CommandGroup>
          )
        })}
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
    { cn: [], us: [], crypto: [] },
  )
}
