'use client'

/**
 * symbol 联想输入(助手 symbol 模糊输入刀)· 轻量 Input + 下拉 div(不上 Command,本场景裸联想更轻)。
 *
 * 数据源:复用 fetchTickers24h('perp', 1000) 全市场 ~527 USDT 永续 ——
 * queryKey ['crypto-tickers','perp'] 与 crypto-market 页【共享 TanStack 缓存】,零新端点。
 * 过滤范式照 crypto-market:endsWith('/USDT') + toUpperCase().includes(q) 本地匹配,下拉前 8 条。
 * 无匹配时允许直接用输入值(后端 normalize_symbol 有补 USDT 兜底)。
 */

import { useMemo, useState } from 'react'

import { Input } from '@/components/ui/input'
import { fetchTickers24h } from '@/lib/api/crypto-market'
import { useQuery } from '@tanstack/react-query'

const MAX_SUGGESTIONS = 8

export function SymbolSuggest({
  value,
  onChange,
  className,
}: {
  value: string
  onChange: (v: string) => void
  className?: string
}) {
  const [open, setOpen] = useState(false)

  // 与 crypto-market 同 key 同参 → 共享缓存(它已加载过则零请求)
  const tickersQ = useQuery({
    queryKey: ['crypto-tickers', 'perp'],
    queryFn: ({ signal }) => fetchTickers24h('perp', 1000, signal),
    retry: 0,
    staleTime: 60_000,
  })

  // 全量 USDT 永续 → 无斜杠形式(ETHUSDT · 与因子表/后端入参形态一致)
  const symbols = useMemo(
    () =>
      (tickersQ.data?.items ?? [])
        .filter((it) => it.symbol.endsWith('/USDT'))
        .map((it) => it.symbol.replace('/', '')),
    [tickersQ.data],
  )

  const q = value.trim().toUpperCase()
  const suggestions = useMemo(
    () => (q.length >= 1 ? symbols.filter((s) => s.includes(q)).slice(0, MAX_SUGGESTIONS) : []),
    [symbols, q],
  )

  return (
    <div className={`relative ${className ?? ''}`}>
      <Input
        value={value}
        onChange={(e) => {
          onChange(e.target.value)
          setOpen(true)
        }}
        onFocus={() => setOpen(true)}
        onBlur={() => setOpen(false)}
        placeholder="BTCUSDT"
      />
      {open && suggestions.length > 0 && (
        <ul className="absolute z-10 mt-1 w-full overflow-hidden rounded-md border border-paper bg-cream shadow-md">
          {suggestions.map((s) => (
            <li key={s}>
              <button
                type="button"
                // onMouseDown 抢在 Input blur 之前选中(blur 会先关下拉,click 就丢了)
                onMouseDown={(e) => {
                  e.preventDefault()
                  onChange(s)
                  setOpen(false)
                }}
                className="block w-full px-3 py-1.5 text-left font-mono text-sm text-foreground transition-colors hover:bg-midas-red-glow/50"
              >
                {s}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
