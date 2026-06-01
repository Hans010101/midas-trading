'use client'

/**
 * 现货详情页 Header(0023 阶段③ · 3.4 批2)· A股 / 美股共用。
 *
 * - 最新价 + 日涨跌:现货日 K(/api/v1/market/kline · 末根 close vs 前根)
 * - 周期切换:15m / 1h / 1d(kline period 子集 · 无 4h · 跟 crypto 详情页一致)
 * - 接不上的字段显示「—」· 不伪造(CLAUDE.md 红线)。
 *
 * 跟 crypto-header 同构,去掉资金费(现货无)· instrument 默认 spot。
 */

import Link from 'next/link'
import { ArrowLeft } from 'lucide-react'

import { WatchlistToggleButton } from '@/components/watchlist/watchlist-toggle-button'
import { useKline } from '@/hooks/use-kline'
import { cn } from '@/lib/utils'
import type { Market, Period } from '@midas/shared'

// 现货主图周期 · kline 存储支持的子集(无 4h)
export const SPOT_PREVIEW_PERIODS: Period[] = ['15m', '1h', '1d']
// ★ 港股周期:hk_source 只支持日 / 周线(无分钟线 · 15m/1h 会 502)→ 详情页只给日线
const HK_PERIODS: Period[] = ['1d']

const MARKET_LABEL: Record<'cn' | 'us' | 'hk', string> = { cn: 'A股', us: '美股', hk: '港股' }
const MARKET_HOME: Record<'cn' | 'us' | 'hk', '/cn-market' | '/us-market' | '/hk-market'> = {
  cn: '/cn-market',
  us: '/us-market',
  hk: '/hk-market',
}

interface SpotHeaderProps {
  symbol: string
  name?: string | null
  market: 'cn' | 'us' | 'hk'
  period: Period
  onPeriodChange: (p: Period) => void
}

function fmtPrice(price: number, market: 'cn' | 'us' | 'hk'): string {
  // 港股价格用 HK$(港币)· A股 ¥ · 美股 $
  const sign = market === 'cn' ? '¥' : market === 'hk' ? 'HK$' : '$'
  return `${sign}${price.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
}

export function SpotHeader({ symbol, name, market, period, onPeriodChange }: SpotHeaderProps) {
  // ★ 港股只给日线(hk_source 无分钟线 · 15m/1h 会 502)· cn/us 给 15m/1h/1d
  const periods = market === 'hk' ? HK_PERIODS : SPOT_PREVIEW_PERIODS
  // 日 K 取末两根算最新价 + 日涨跌 · 现货(spot)· 跟主图 / 缠论 / AI 同源
  const dailyKline = useKline({
    symbol,
    market: market as Market,
    period: '1d',
    limit: 2,
  })

  const items = dailyKline.data?.items ?? []
  const last = items.at(-1)
  const prev = items.at(-2)
  const price = last?.close ?? null
  const changePct =
    last && prev && prev.close !== 0
      ? ((last.close - prev.close) / prev.close) * 100
      : null
  const up = changePct !== null && changePct >= 0

  return (
    <header className="border-b border-paper bg-surface-card px-6 py-3">
      <div className="mx-auto flex max-w-[1600px] flex-wrap items-center gap-x-6 gap-y-2">
        <Link
          href={MARKET_HOME[market]}
          className="flex items-center gap-1 text-xs text-muted-foreground transition-colors hover:text-midas-red"
        >
          <ArrowLeft className="h-3.5 w-3.5" />
          {MARKET_LABEL[market]}首页
        </Link>

        <div className="flex items-baseline gap-2">
          <span className="font-serif text-2xl font-bold">{symbol}</span>
          {name && <span className="text-sm text-muted-foreground">{name}</span>}
          <span className={cn('font-mono text-lg font-bold', up ? 'text-up' : 'text-down')}>
            {price !== null ? fmtPrice(price, market) : '—'}
          </span>
          <span className={cn('font-mono text-sm', up ? 'text-up' : 'text-down')}>
            {changePct !== null ? `${up ? '+' : ''}${changePct.toFixed(2)}%` : ''}
          </span>
          <span className="text-[10px] text-muted-foreground/50">日涨跌</span>
        </div>

        <span className="rounded-md border border-paper px-2 py-0.5 text-xs text-muted-foreground">
          {MARKET_LABEL[market]} · 现货
        </span>
        <WatchlistToggleButton symbol={symbol} market={market} />

        {/* 周期切换 · 驱动主图 */}
        <div className="flex gap-1 text-xs">
          {periods.map((p) => (
            <button
              key={p}
              type="button"
              onClick={() => onPeriodChange(p)}
              className={cn(
                'rounded px-2 py-1 transition-colors',
                p === period
                  ? 'bg-midas-red-glow text-midas-red'
                  : 'text-muted-foreground hover:text-foreground',
              )}
            >
              {p}
            </button>
          ))}
        </div>

      </div>
    </header>
  )
}
