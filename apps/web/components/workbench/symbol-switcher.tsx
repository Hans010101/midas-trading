'use client'

/**
 * 顶部当前标的搜索切换器(段 1 补丁 A)。
 *
 * 跟右栏 Cmd+K 是两个独立功能:
 * - 此组件:点 chart 顶部 symbol 弹搜索 → 选中后 setSymbol(切当前 K 线图,临时)
 * - 右栏 Cmd+K:搜索 + POST /watchlist(加入自选,持久)
 *
 * 搜索范围限当前市场 Tab(在加密 Tab 搜加密,美股 Tab 搜美股)。
 */

import { ChevronDown } from 'lucide-react'
import { useEffect, useState } from 'react'

import {
  CommandDialog,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from '@/components/ui/command'
import { useSymbolSearch } from '@/hooks/use-symbol-search'
import { useWorkbenchStore } from '@/lib/store/workbench-store'
import { MARKET_LABEL } from '@/lib/format-money'
import { cn } from '@/lib/utils'

export function SymbolSwitcher() {
  const symbol = useWorkbenchStore((s) => s.symbol)
  const market = useWorkbenchStore((s) => s.market)
  const setSymbol = useWorkbenchStore((s) => s.setSymbol)

  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState('')
  const { data: results = [], isFetching } = useSymbolSearch(query, market)

  // 切换 market 时关闭弹窗(避免上个 market 的结果残留)
  useEffect(() => {
    setOpen(false)
    setQuery('')
  }, [market])

  function handleSelect(s: string) {
    setSymbol(s)
    setOpen(false)
    setQuery('')
  }

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        title={`点击或聚焦后输入搜索 ${MARKET_LABEL[market]} 标的`}
        className="group flex items-baseline gap-2 rounded-md px-2 py-1 transition-colors hover:bg-midas-red-glow/40"
      >
        <h2 className="font-serif text-xl font-bold text-foreground">{symbol}</h2>
        <span className="font-mono text-xs uppercase text-muted-foreground">
          {market}
        </span>
        <ChevronDown className="h-3.5 w-3.5 text-muted-foreground/70 transition-transform group-hover:text-midas-red" />
      </button>

      <CommandDialog open={open} onOpenChange={setOpen}>
        <CommandInput
          placeholder={`在 ${MARKET_LABEL[market]} 中搜索标的(代码 / 名称)...`}
          value={query}
          onValueChange={setQuery}
        />
        <CommandList>
          {query.trim().length === 0 && (
            <div className="px-3 py-4 text-center text-xs text-muted-foreground/70">
              输入关键词 · 当前市场 {MARKET_LABEL[market]}
            </div>
          )}
          {query.trim().length >= 1 && !isFetching && results.length === 0 && (
            <CommandEmpty>没有匹配标的</CommandEmpty>
          )}
          {results.length > 0 && (
            <CommandGroup heading={`${MARKET_LABEL[market]} · ${results.length} 个结果`}>
              {results.map((item) => (
                <CommandItem
                  key={`${item.market}-${item.symbol}`}
                  value={`${item.symbol} ${item.name} ${item.name_en}`}
                  onSelect={() => handleSelect(item.symbol)}
                  className={cn(
                    'flex items-center justify-between gap-3',
                    item.symbol === symbol && 'bg-midas-red-glow/50',
                  )}
                >
                  <span className="flex min-w-0 items-center gap-3">
                    <span className="font-mono text-xs text-foreground">{item.symbol}</span>
                    <span className="truncate text-sm text-foreground">{item.name}</span>
                  </span>
                  {item.symbol === symbol && (
                    <span className="text-[10px] text-midas-red">当前</span>
                  )}
                </CommandItem>
              ))}
            </CommandGroup>
          )}
        </CommandList>
      </CommandDialog>
    </>
  )
}
