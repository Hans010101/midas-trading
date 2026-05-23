'use client'

/**
 * M2-D · 详情页 Header · 真实数据。
 *
 * - 最新价 + 日涨跌:取自现货日 K(/api/v1/market/kline · 末根 close vs 前根)
 * - 资金费率 + 下次结算:取自合约 info(/api/v1/crypto/futures/{sym}/info)
 * - 周期切换:15m / 1h / 1d(kline period enum 无 4h · 见交付说明)
 *
 * 接不上的字段一律显示「—」· 不伪造数值(CLAUDE.md 红线)。
 */

import { VirtualBadge } from '@/components/ui/virtual-badge'
import { useFuturesInfo } from '@/hooks/use-crypto'
import { useKline } from '@/hooks/use-kline'
import { cn } from '@/lib/utils'
import type { Period } from '@midas/shared'

// 主图周期 · kline 存储支持的子集(无 4h)
export const PREVIEW_PERIODS: Period[] = ['15m', '1h', '1d']

interface CryptoHeaderProps {
  /** ccxt 风格 'BTC/USDT' */
  klineSymbol: string
  /** Binance 风格 'BTCUSDT' */
  futuresSymbol: string
  period: Period
  onPeriodChange: (p: Period) => void
}

export function CryptoHeader({
  klineSymbol,
  futuresSymbol,
  period,
  onPeriodChange,
}: CryptoHeaderProps) {
  // 日 K 取末两根算最新价 + 日涨跌 · 合约(perp)· 跟主图/缠论/AI 同源,JCT 这类无现货对的币也能出价
  const dailyKline = useKline({ symbol: klineSymbol, market: 'crypto', period: '1d', limit: 2, instrument: 'perp' })
  const info = useFuturesInfo(futuresSymbol)

  const items = dailyKline.data?.items ?? []
  const last = items.at(-1)
  const prev = items.at(-2)
  const price = last?.close ?? null
  const changePct =
    last && prev && prev.close !== 0
      ? ((last.close - prev.close) / prev.close) * 100
      : null

  const fundingRate = info.data?.last_funding_rate ?? null
  const nextFunding = info.data?.next_funding_time ?? null

  const up = changePct !== null && changePct >= 0

  return (
    <header className="border-b border-paper bg-cream/40 px-6 py-3">
      <div className="mx-auto flex max-w-[1600px] flex-wrap items-center gap-x-6 gap-y-2">
        <div className="flex items-baseline gap-2">
          <span className="font-serif text-2xl font-bold">{klineSymbol}</span>
          <span className={cn('font-mono text-lg font-bold', up ? 'text-bull' : 'text-bear')}>
            {price !== null ? `$${price.toLocaleString('en-US', { maximumFractionDigits: 2 })}` : '—'}
          </span>
          <span className={cn('font-mono text-sm', up ? 'text-bull' : 'text-bear')}>
            {changePct !== null ? `${up ? '+' : ''}${changePct.toFixed(2)}%` : ''}
          </span>
          <span className="text-[10px] text-muted-foreground/50">日涨跌</span>
        </div>

        <VirtualBadge size="sm" />

        {/* 现货 / 合约 tab · 本页聚焦合约 · 现货切换 M2-B 待接 */}
        <div className="flex overflow-hidden rounded-md border border-paper text-sm">
          <span className="bg-midas-red px-3 py-1 text-white">合约</span>
          <span className="px-3 py-1 text-muted-foreground/50" title="现货切换 · M2-B 待接">
            现货
          </span>
        </div>

        {/* 周期切换 · 驱动主图 */}
        <div className="flex gap-1 text-xs">
          {PREVIEW_PERIODS.map((p) => (
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

        <div className="ml-auto font-mono text-xs text-muted-foreground">
          {fundingRate !== null ? (
            <>
              资金费率{' '}
              <span className={fundingRate >= 0 ? 'text-bull' : 'text-bear'}>
                {fundingRate >= 0 ? '+' : ''}
                {(fundingRate * 100).toFixed(4)}%
              </span>
              {nextFunding && ` · 下次结算 ${new Date(nextFunding).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })}`}
            </>
          ) : (
            <span className="text-muted-foreground/50">资金费率 — · 待预热</span>
          )}
        </div>
      </div>
    </header>
  )
}
