'use client'

/**
 * 工作台中央区:顶部信号条占位 + K 线图 + 底部周期切换 + 指标面板。
 *
 * 信号条 + AI 决策卡 是 M1 才实装的元素,M0 留 "M1 待实装" 占位。
 */

import { KlineChart } from '@/components/chart/kline-chart'
import { IndicatorPanel } from '@/components/workbench/indicator-panel'
import { KlineContextMenu } from '@/components/workbench/kline-context-menu'
import { PeriodSwitcher } from '@/components/workbench/period-switcher'
import { SymbolSwitcher } from '@/components/workbench/symbol-switcher'
import { useWorkbenchStore } from '@/lib/store/workbench-store'

export function ChartArea() {
  const market = useWorkbenchStore((s) => s.market)
  const symbol = useWorkbenchStore((s) => s.symbol)
  const period = useWorkbenchStore((s) => s.period)
  const indicators = useWorkbenchStore((s) => s.indicators)
  const setPeriod = useWorkbenchStore((s) => s.setPeriod)

  return (
    <section className="flex flex-1 flex-col overflow-hidden bg-background">
      {/* 顶部信号条占位 · M1 实装 · 见 0001 视觉边界 */}
      <div className="flex h-10 shrink-0 items-center justify-center border-b border-paper bg-cream/50">
        <span className="text-xs text-muted-foreground/70">
          信号条(信号强度 / 多空一致性 / 主力意图)· M1 待实装
        </span>
      </div>

      {/* K 线区 + 周期 + 指标控制条 */}
      <div className="flex flex-1 flex-col overflow-hidden p-4">
        <div className="mb-3 flex shrink-0 items-center justify-between">
          <SymbolSwitcher />
          <div className="flex items-center gap-3">
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
            />
          </div>
        </KlineContextMenu>
      </div>
    </section>
  )
}
