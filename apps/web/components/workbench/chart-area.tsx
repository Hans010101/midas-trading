'use client'

/**
 * 工作台中央区:顶部信号条占位 + 标的切换 + 缠论开关 + 指标 + 周期 + K 线。
 *
 * K 线区右键弹下单菜单(M0 收口实装)。
 * 缠论开关默认关 · 开启时 ChanOverlay 在图上叠加笔/中枢/分型(M1 第一波)。
 */

import { ChanOverlay } from '@/components/chart/chan-overlay'
import { KlineChart } from '@/components/chart/kline-chart'
import { ChanToggle } from '@/components/workbench/chan-toggle'
import { IndicatorPanel } from '@/components/workbench/indicator-panel'
import { KlineContextMenu } from '@/components/workbench/kline-context-menu'
import { PeriodSwitcher } from '@/components/workbench/period-switcher'
import { SymbolSwitcher } from '@/components/workbench/symbol-switcher'
import { useChartInstance } from '@/lib/chart-instance-context'
import { useWorkbenchStore } from '@/lib/store/workbench-store'

export function ChartArea() {
  const market = useWorkbenchStore((s) => s.market)
  const symbol = useWorkbenchStore((s) => s.symbol)
  const period = useWorkbenchStore((s) => s.period)
  const indicators = useWorkbenchStore((s) => s.indicators)
  const setPeriod = useWorkbenchStore((s) => s.setPeriod)
  const { chart, setChart } = useChartInstance()

  return (
    <section className="flex flex-1 flex-col overflow-hidden bg-background">
      {/* 顶部信号条占位 · M1 待实装(AI 决策卡)*/}
      <div className="flex h-10 shrink-0 items-center justify-center border-b border-paper bg-cream/50">
        <span className="text-xs text-muted-foreground/70">
          信号条(信号强度 / 多空一致性 / 主力意图)· M1 待实装
        </span>
      </div>

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
      </div>
    </section>
  )
}
