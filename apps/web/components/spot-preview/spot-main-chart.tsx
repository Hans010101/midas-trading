'use client'

/**
 * 现货详情页主图(0023 阶段③ · 3.4 批2)· A股 / 美股共用 · 复用工作台同款组件。
 *
 *   · KlineChart   → /api/v1/market/kline(instrument 默认 spot)· BOLL 主图叠加 + MACD 副图
 *   · ChanOverlay  → /api/v1/analysis/chan(props 驱动 · 不读 workbench store)
 *
 * 三图层独立开关(默认全开):布林带 / MACD / 缠论标注。
 * MACD 红涨绿跌 + DIF 帝王金 / DEA 中国红;BOLL 中性灰,避开缠论用色。
 * 跟 crypto-main-chart 同构 · 仅 market 参数化 + 现货(无 instrument=perp)。
 */

import type { Chart } from 'klinecharts'
import { useMemo, useState } from 'react'

import { ChanOverlay } from '@/components/chart/chan-overlay'
import { KlineChart } from '@/components/chart/kline-chart'
import type { IndicatorName } from '@/lib/store/workbench-store'
import { cn } from '@/lib/utils'
import type { Market, Period } from '@midas/shared'

// MACD · 红涨绿跌 + DIF 帝王金 / DEA 中国红(CLAUDE.md 视觉系统)
const MACD_STYLES = {
  bars: [{ upColor: '#DC143C', downColor: '#0F6E5F', noChangeColor: '#94949C' }],
  lines: [{ color: '#B8860B' }, { color: '#C8102E' }],
}

// 布林带 · 中性灰细线 · 避开缠论用色(金=笔 / #6482A0=中枢 / 红绿=分型)
const BOLL_STYLES = {
  lines: [
    { color: '#8C8C8C', size: 1 },
    { color: '#8C8C8C', size: 1 },
    { color: '#8C8C8C', size: 1 },
  ],
}

interface SpotMainChartProps {
  symbol: string
  market: 'cn' | 'us'
  period: Period
}

export function SpotMainChart({ symbol, market, period }: SpotMainChartProps) {
  const [chart, setChart] = useState<Chart | null>(null)
  const [chanEnabled, setChanEnabled] = useState(true)
  const [bollEnabled, setBollEnabled] = useState(true)
  const [macdEnabled, setMacdEnabled] = useState(true)

  const indicators = useMemo<Record<IndicatorName, boolean>>(
    () => ({ MA: false, BOLL: bollEnabled, MACD: macdEnabled, RSI: false }),
    [bollEnabled, macdEnabled],
  )
  const indicatorStyles = useMemo(
    () => ({
      MACD: MACD_STYLES as Record<string, unknown>,
      BOLL: BOLL_STYLES as Record<string, unknown>,
    }),
    [],
  )

  return (
    <div className="rounded-lg border border-paper bg-surface-card p-3">
      <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
        <div>
          <span className="font-serif text-sm font-bold">主图:K 线 + 布林带 + MACD + 缠论</span>
          <span className="ml-2 text-[11px] text-muted-foreground/50">
            BOLL(20,2)· MACD(12,26,9)· 笔(金)/ 分型 / 中枢
          </span>
        </div>
        <div className="flex items-center gap-2">
          <ToggleChip label="布林带" on={bollEnabled} onClick={() => setBollEnabled((v) => !v)} />
          <ToggleChip label="MACD" on={macdEnabled} onClick={() => setMacdEnabled((v) => !v)} />
          <ToggleChip label="缠论标注" on={chanEnabled} onClick={() => setChanEnabled((v) => !v)} />
        </div>
      </div>

      <div className="h-[460px] overflow-hidden rounded-md border border-paper">
        <KlineChart
          symbol={symbol}
          market={market as Market}
          period={period}
          indicators={indicators}
          indicatorStyles={indicatorStyles}
          onChartReady={setChart}
        />
      </div>

      {/* 缠论标注层 · props 驱动(不读 workbench store)· 现货 K 线缠论 */}
      <ChanOverlay
        chart={chart}
        symbol={symbol}
        market={market as Market}
        period={period}
        enabled={chanEnabled}
      />
    </div>
  )
}

function ToggleChip({ label, on, onClick }: { label: string; on: boolean; onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        'rounded-md border px-3 py-1 text-xs transition-colors',
        on
          ? 'border-gold bg-gold/10 text-gold'
          : 'border-paper text-muted-foreground hover:border-gold/60',
      )}
    >
      {label} {on ? '开' : '关'}
    </button>
  )
}
