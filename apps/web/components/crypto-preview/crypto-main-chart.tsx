'use client'

/**
 * M2-D · 主图 · 真实 K 线 + 缠论标注。
 *
 * 复用工作台同款组件:
 *   · KlineChart      → /api/v1/market/kline(market=crypto · symbol=BTC/USDT)
 *   · ChanOverlay     → /api/v1/analysis/chan(props 驱动 · 不污染 workbench store)
 *
 * 缠论开关本地 state(默认开 · 让产品方一眼看到笔/中枢/分型标注效果)。
 * 周期由父组件传入(15m / 1h / 1d · kline period enum 无 4h · 见交付说明)。
 */

import type { Chart } from 'klinecharts'
import { useState } from 'react'

import { ChanOverlay } from '@/components/chart/chan-overlay'
import { KlineChart } from '@/components/chart/kline-chart'
import { cn } from '@/lib/utils'
import type { Period } from '@midas/shared'

interface CryptoMainChartProps {
  /** ccxt 风格 symbol · 'BTC/USDT' */
  symbol: string
  period: Period
}

export function CryptoMainChart({ symbol, period }: CryptoMainChartProps) {
  const [chart, setChart] = useState<Chart | null>(null)
  const [chanEnabled, setChanEnabled] = useState(true)

  return (
    <div className="rounded-lg border border-paper bg-cream/30 p-3">
      <div className="mb-2 flex items-center justify-between">
        <div>
          <span className="font-serif text-sm font-bold">主图:K 线 + 缠论标注</span>
          <span className="ml-2 text-[11px] text-muted-foreground/50">
            笔(金)· 顶/底分型 · 中枢(淡灰蓝)
          </span>
        </div>
        <button
          type="button"
          onClick={() => setChanEnabled((v) => !v)}
          className={cn(
            'rounded-md border px-3 py-1 text-xs transition-colors',
            chanEnabled
              ? 'border-gold bg-gold/10 text-gold'
              : 'border-paper text-muted-foreground hover:border-gold/60',
          )}
        >
          缠论标注 {chanEnabled ? '开' : '关'}
        </button>
      </div>

      <div className="h-[420px] overflow-hidden rounded-md border border-paper">
        <KlineChart
          symbol={symbol}
          market="crypto"
          period={period}
          onChartReady={setChart}
        />
      </div>

      {/* 缠论标注层 · props 驱动(不读 workbench store)*/}
      <ChanOverlay
        chart={chart}
        symbol={symbol}
        market="crypto"
        period={period}
        enabled={chanEnabled}
      />
    </div>
  )
}
