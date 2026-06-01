'use client'

/**
 * 工作台中央区:顶部信号条占位 + 标的切换 + 缠论开关 + 指标 + 周期 + K 线。
 *
 * K 线区右键弹下单菜单(M0 收口实装)。
 * 缠论开关默认关 · 开启时 ChanOverlay 在图上叠加笔/中枢/分型(M1 第一波)。
 */

import { useState } from 'react'

import { ChanOverlay } from '@/components/chart/chan-overlay'
import { KlineChart } from '@/components/chart/kline-chart'
import { StrategyOverlay } from '@/components/chart/strategy-overlay'
import { StrategyPanel } from '@/components/chart/strategy-panel'
import { ChanToggle } from '@/components/workbench/chan-toggle'
import { IndicatorPanel } from '@/components/workbench/indicator-panel'
import { KlineContextMenu } from '@/components/workbench/kline-context-menu'
import { PeriodSwitcher } from '@/components/workbench/period-switcher'
import { SignalBar } from '@/components/workbench/signal-bar'
import { SymbolSwitcher } from '@/components/workbench/symbol-switcher'
import type { StrategyKind } from '@/lib/api/strategy'
import { useChartInstance } from '@/lib/chart-instance-context'
import { useWorkbenchStore } from '@/lib/store/workbench-store'

export function ChartArea() {
  const market = useWorkbenchStore((s) => s.market)
  const symbol = useWorkbenchStore((s) => s.symbol)
  const period = useWorkbenchStore((s) => s.period)
  const indicators = useWorkbenchStore((s) => s.indicators)
  const setPeriod = useWorkbenchStore((s) => s.setPeriod)
  const { chart, setChart } = useChartInstance()
  // 形态A 策略信号(默认关 · 不干扰现有缠论/指标 · 工作台 local state)
  const [strategy, setStrategy] = useState<StrategyKind>('ma_cross')
  const [strategyEnabled, setStrategyEnabled] = useState(false)

  return (
    <section className="flex flex-1 flex-col overflow-hidden bg-background">
      {/* 顶部信号条 · M1 二波实装(0012 ADR Checkpoint Z)*/}
      <SignalBar />

      {/* K 线区 + 缠论开关 + 周期 + 指标控制条 */}
      <div className="flex flex-1 flex-col overflow-hidden p-4">
        <div className="mb-3 flex shrink-0 items-center justify-between">
          <SymbolSwitcher />
          <div className="flex items-center gap-3">
            <ChanToggle />
            <IndicatorPanel />
            <PeriodSwitcher />
          </div>
        </div>

        <KlineContextMenu>
          <div className="flex-1 overflow-hidden rounded-lg border border-paper">
            <KlineChart
              symbol={symbol}
              market={market}
              period={period}
              indicators={indicators}
              onSwitchToDaily={() => setPeriod('1d')}
              onChartReady={setChart}
            />
          </div>
        </KlineContextMenu>

        {/* 缠论标注层 · 通过 context 拿 chart instance · enabled 关时不画 */}
        <ChanOverlay chart={chart} />
        {/* 策略信号标注层 · 独立 groupId(midas-strategy-overlay)· 不干扰缠论 */}
        <StrategyOverlay
          chart={chart}
          symbol={symbol}
          market={market}
          period={period}
          strategy={strategy}
          enabled={strategyEnabled}
        />

        {/* AI 策略面板 · 工作台底部(展示型 · 不下单 · 默认关)*/}
        <div className="mt-3 shrink-0">
          <StrategyPanel
            symbol={symbol}
            market={market}
            period={period}
            strategy={strategy}
            onStrategyChange={setStrategy}
            enabled={strategyEnabled}
            onToggle={() => setStrategyEnabled((v) => !v)}
          />
        </div>
      </div>
    </section>
  )
}
