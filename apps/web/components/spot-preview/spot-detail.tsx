'use client'

/**
 * 现货个股详情页(0023 阶段③ · 3.4 批2)· A股 / 美股共用 · market 参数化。
 *
 * 布局沿用 crypto-preview(产品方已验收):顶部 Header · 左主区(主图)· 右侧栏(AI 决策卡 + 下单区)。
 * 复用工作台 / 0008 现有组件(K线 / 缠论 / AI / 下单)· 详情页本体只做编排。
 *
 * 标的由 URL ?symbol=（&name=)驱动 · 无参数回落到该市场 demo 标的(绝不崩、绝不留空)。
 * 路由 /cn-preview /us-preview · middleware 不保护(匿名可看图,下单时引导登录)。
 *
 * 红线:全程虚拟资金 · 美股卖空仅虚拟负持仓记账 · 绝不接真实交易。
 */

import { useSearchParams } from 'next/navigation'
import { useMemo, useState } from 'react'

import { AiDecisionCard } from '@/components/workbench/ai-decision-card'
import { SpotHeader } from '@/components/spot-preview/spot-header'
import { SpotMainChart } from '@/components/spot-preview/spot-main-chart'
import { SpotOrderPanel } from '@/components/spot-preview/spot-order-panel'
import type { Period } from '@midas/shared'

const DEFAULTS: Record<'cn' | 'us', { symbol: string; name: string }> = {
  cn: { symbol: '600519', name: '贵州茅台' },
  us: { symbol: 'NVDA', name: 'NVIDIA' },
}

interface SpotDetailProps {
  market: 'cn' | 'us'
}

export function SpotDetail({ market }: SpotDetailProps) {
  const searchParams = useSearchParams()
  const { symbol, name } = useMemo(() => {
    const raw = (searchParams.get('symbol') ?? '').trim()
    if (!raw) return DEFAULTS[market]
    return { symbol: raw.toUpperCase(), name: (searchParams.get('name') ?? '').trim() }
  }, [searchParams, market])
  const [period, setPeriod] = useState<Period>('1d')

  return (
    <main className="min-h-screen bg-background text-foreground">
      <SpotHeader
        symbol={symbol}
        name={name}
        market={market}
        period={period}
        onPeriodChange={setPeriod}
      />

      <div className="mx-auto flex max-w-[1600px] flex-col gap-4 px-4 py-4 lg:flex-row">
        {/* 左主区:K 线 + 缠论 + 指标 */}
        <div className="flex-1 space-y-4">
          <SpotMainChart symbol={symbol} market={market} period={period} />
        </div>

        {/* 右侧栏:AI 决策卡(复用工作台)+ 下单区(差异化) */}
        <aside className="w-full shrink-0 space-y-4 lg:w-[360px]">
          <AiDecisionCard symbol={symbol} market={market} period={period} />
          <SpotOrderPanel symbol={symbol} name={name} market={market} />
        </aside>
      </div>
    </main>
  )
}
