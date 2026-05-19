/**
 * /workbench - K 线工作台。
 *
 * G Checkpoint:占位实现,只渲染一只标的 BTC/USDT 1d 验证 KLineChart 通。
 * H Checkpoint 会扩展到三栏 + 市场 Tab + 周期切换 + 4 指标 + 标的切换。
 */

import { KlineChart } from '@/components/chart/kline-chart'

export default function WorkbenchPage() {
  return (
    <main className="min-h-screen bg-background p-8">
      <div className="mx-auto max-w-6xl space-y-4">
        <header className="space-y-1">
          <h1 className="font-serif text-3xl font-bold text-foreground">
            点金 <span className="text-midas-red">Midas</span> · 工作台
          </h1>
          <p className="text-sm text-muted-foreground">
            G Checkpoint 占位 · 验证 KLineChart 渲染 · 工作台完整布局在 H Checkpoint 落地
          </p>
        </header>

        <section className="h-[560px] w-full rounded-lg border border-paper bg-cream p-4">
          <KlineChart symbol="BTC/USDT" market="crypto" period="1d" />
        </section>

        <footer className="text-xs text-muted-foreground/70">
          模拟交易,不构成投资建议
        </footer>
      </div>
    </main>
  )
}
