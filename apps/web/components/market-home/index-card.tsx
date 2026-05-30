/**
 * 指标卡(共用组件 · ADR 0035 抽出)。
 *
 * 原内联于 market-home-page 的 IndexCard,抽成共用 + 单位感知,给:
 *  - 市场首页(cn/us 大盘指数 · unit='point' · 渲染与抽出前【字节一致】· 零回归)
 *  - 全球概览(指数/商品/外汇/债券/加密 · 按 unit 格式化:point/price/rate/yield_pct+bp)
 * 涨红跌绿沿用项目视觉系统(text-up / text-down)。
 */

import { Panel } from '@/components/ui/panel'
import { cn } from '@/lib/utils'

export type QuoteUnit = 'point' | 'price' | 'rate' | 'yield_pct'

function fmtValue(v: number, unit: QuoteUnit): string {
  if (unit === 'yield_pct') return `${v.toFixed(3)}%`
  const dp = unit === 'rate' ? 4 : 2
  return v.toLocaleString('en-US', { minimumFractionDigits: dp, maximumFractionDigits: dp })
}

function fmtChange(changeAbs: number, changePct: number, unit: QuoteUnit): string {
  // 债券收益率:涨跌用基点 bp(决策③)· 不显示相对 %
  if (unit === 'yield_pct') {
    const bp = changeAbs * 100
    return `${bp >= 0 ? '+' : ''}${bp.toFixed(1)} bp`
  }
  const dp = unit === 'rate' ? 4 : 2
  const signAbs = changeAbs >= 0 ? '+' : ''
  const signPct = changePct >= 0 ? '+' : ''
  return `${signAbs}${changeAbs.toFixed(dp)} (${signPct}${changePct.toFixed(2)}%)`
}

export function QuoteCard({
  name,
  lastPoint,
  changePoint,
  changePct,
  unit = 'point',
}: {
  name: string
  lastPoint: number
  changePoint: number
  changePct: number
  unit?: QuoteUnit
}) {
  const up = changePct >= 0
  return (
    <Panel padding="md">
      <div className="truncate text-xs text-muted-foreground">{name}</div>
      <div className={cn('mt-1 font-mono text-2xl font-bold', up ? 'text-up' : 'text-down')}>
        {fmtValue(lastPoint, unit)}
      </div>
      <div className={cn('mt-0.5 font-mono text-xs', up ? 'text-up' : 'text-down')}>
        {fmtChange(changePoint, changePct, unit)}
      </div>
    </Panel>
  )
}
