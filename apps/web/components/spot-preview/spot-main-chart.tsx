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
import { StrategyOverlay } from '@/components/chart/strategy-overlay'
import { StrategyPanel } from '@/components/chart/strategy-panel'
import type { StrategyKind } from '@/lib/api/strategy'
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
  // 港股阶段二:hk 复用现货主图(K线 + 缠论 + BOLL/MACD 指标),
  // 但 market==='hk' 时 gate 掉形态A 策略面板/信号(strategy API 未注入 hk 会 500 · 港股不接 AI 策略)
  market: 'cn' | 'us' | 'hk'
  period: Period
}

export function SpotMainChart({ symbol, market, period }: SpotMainChartProps) {
  const [chart, setChart] = useState<Chart | null>(null)
  const [chanEnabled, setChanEnabled] = useState(true)
  const [bollEnabled, setBollEnabled] = useState(true)
  const [macdEnabled, setMacdEnabled] = useState(true)
  // 形态A 策略信号(默认关 · 不干扰现有缠论/指标)
  const [strategy, setStrategy] = useState<StrategyKind>('ma_cross')
  const [strategyEnabled, setStrategyEnabled] = useState(false)

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
    <div className="space-y-3">
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
      {/* 策略信号标注层 · 独立 groupId · 不干扰缠论 · 现货默认 spot
          ★ 港股阶段二不渲染(形态A 策略=AI 信号 · /analysis/strategy-* 未注入 hk 会 500 · 港股只看 K线+缠论+指标) */}
      {market !== 'hk' && (
        <StrategyOverlay
          chart={chart}
          symbol={symbol}
          market={market as Market}
          period={period}
          strategy={strategy}
          enabled={strategyEnabled}
        />
      )}
      </div>

      {/* AI 策略面板:选择器 + 推荐 + 触发状态(展示型 · 不下单)
          ★ 港股阶段二不渲染(同上 · 港股不接 AI 策略 · 不给开启入口 → strategyEnabled 恒 false · 留后续) */}
      {market !== 'hk' && (
        <StrategyPanel
          symbol={symbol}
          market={market as Market}
          period={period}
          strategy={strategy}
          onStrategyChange={setStrategy}
          enabled={strategyEnabled}
          onToggle={() => setStrategyEnabled((v) => !v)}
        />
      )}
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
