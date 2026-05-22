'use client'

/**
 * M2-D · 主图 · 真实 K 线 + 布林带 + MACD 副图 + 缠论标注。
 *
 * 复用工作台同款组件:
 *   · KlineChart   → /api/v1/market/kline · 用 indicators 开 BOLL(主图叠加)+ MACD(副图)
 *                    指标计算走 klinecharts 内置 BOLL / MACD(标准参数 20,2 / 12,26,9)
 *   · ChanOverlay  → /api/v1/analysis/chan(props 驱动 · 不污染 workbench store)
 *
 * 三个图层独立开关(默认全开):布林带 / MACD / 缠论标注。
 * 布林带在主图叠加,跟缠论标注(笔/中枢/分型)同层共存,不冲突
 * (BOLL 走 indicator,缠论走 overlay,klinecharts 两套机制互不覆盖)。
 *
 * MACD 柱:红涨绿跌(A 股传统 · CLAUDE.md 视觉系统)· 覆盖 klinecharts 默认的绿涨红跌。
 * DIF 帝王金 / DEA 中国红 · 跟点金主色一致。
 * 周期由父组件传入(15m / 1h / 1d · kline period enum 无 4h · 见交付说明)。
 */

import type { Chart } from 'klinecharts'
import { useMemo, useState } from 'react'

import { ChanOverlay } from '@/components/chart/chan-overlay'
import { KlineChart } from '@/components/chart/kline-chart'
import { cn } from '@/lib/utils'
import type { IndicatorName } from '@/lib/store/workbench-store'
import type { Period } from '@midas/shared'

// MACD 样式覆盖 · 红涨绿跌 + DIF 帝王金 / DEA 中国红(CLAUDE.md 视觉系统)
// MACD 只有一个柱图 figure,bars[0] 控制柱的涨跌色,跟 figure 顺序无关 · 稳。
const MACD_STYLES = {
  bars: [{ upColor: '#DC143C', downColor: '#0F6E5F', noChangeColor: '#94949C' }],
  lines: [{ color: '#B8860B' }, { color: '#C8102E' }], // DIF 帝王金 / DEA 中国红
}

interface CryptoMainChartProps {
  /** ccxt 风格 symbol · 'BTC/USDT' */
  symbol: string
  period: Period
}

export function CryptoMainChart({ symbol, period }: CryptoMainChartProps) {
  const [chart, setChart] = useState<Chart | null>(null)
  const [chanEnabled, setChanEnabled] = useState(true)
  const [bollEnabled, setBollEnabled] = useState(true)
  const [macdEnabled, setMacdEnabled] = useState(true)

  // useMemo 稳定引用 · 否则每次 render 新对象会让 KlineChart 反复重建指标
  const indicators = useMemo<Record<IndicatorName, boolean>>(
    () => ({ MA: false, BOLL: bollEnabled, MACD: macdEnabled, RSI: false }),
    [bollEnabled, macdEnabled],
  )
  const indicatorStyles = useMemo(
    () => ({ MACD: MACD_STYLES as Record<string, unknown> }),
    [],
  )

  return (
    <div className="rounded-lg border border-paper bg-cream/30 p-3">
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
          market="crypto"
          period={period}
          indicators={indicators}
          indicatorStyles={indicatorStyles}
          onChartReady={setChart}
        />
      </div>

      {/* 缠论标注层 · props 驱动(不读 workbench store)· 跟布林带同层共存 */}
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
