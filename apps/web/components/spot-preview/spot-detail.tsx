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

import { TopNav } from '@/components/layout/top-nav'
import { AiDecisionCard } from '@/components/workbench/ai-decision-card'
import { ConditionalOrdersList } from '@/components/trading/conditional-orders-list'
import { SpotHeader } from '@/components/spot-preview/spot-header'
import { SpotMainChart } from '@/components/spot-preview/spot-main-chart'
import { SpotOrderPanel } from '@/components/spot-preview/spot-order-panel'
import type { Period } from '@midas/shared'

const DEFAULTS: Record<'cn' | 'us' | 'hk', { symbol: string; name: string }> = {
  cn: { symbol: '600519', name: '贵州茅台' },
  us: { symbol: 'NVDA', name: 'NVIDIA' },
  hk: { symbol: '00700', name: '腾讯控股' },
}

interface SpotDetailProps {
  // 港股阶段二:hk 复用现货详情页,但 market==='hk' 时 gate 掉 AI 决策卡 + 下单区(见 aside)
  market: 'cn' | 'us' | 'hk'
  // ★SEO 批7:路径段静态壳 `/{cn,us,hk}/[symbol]` 传入 symbol(+可选 name)· 缺省回退 searchParams
  symbol?: string
  name?: string
}

export function SpotDetail({ market, symbol: propSymbol, name: propName }: SpotDetailProps) {
  // ★优先 prop(路径段壳)· 回退 useSearchParams(旧 `?symbol=` 页现状不变 · 缺省逐字节等于改造前)。
  const searchParams = useSearchParams()
  const { symbol, name } = useMemo(() => {
    const raw = (propSymbol ?? searchParams.get('symbol') ?? '').trim()
    if (!raw) return DEFAULTS[market]
    return { symbol: raw.toUpperCase(), name: (propName ?? searchParams.get('name') ?? '').trim() }
  }, [searchParams, market, propSymbol, propName])
  // 默认周期:cn/us 用 1h(日内 · 15m/1h/1d 可切);★港股只支持日/周线(hk_source 无分钟线)→ 默认且仅 1d
  const [period, setPeriod] = useState<Period>(market === 'hk' ? '1d' : '1h')

  return (
    <main className="min-h-screen bg-background text-foreground">
      <TopNav />
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

        {/* 右侧栏:AI 决策卡(复用工作台)+ 下单区
            ★ 港股阶段三单元1:解 gate AI 决策卡 —— hk 也渲染 AiDecisionCard(后端已补 hk prompt/TTL/source)。
            ★ 港股阶段三单元3:解 gate 下单区 —— hk 也渲染 SpotOrderPanel(按手 board lot 取整 + 印花税/佣金 + 二次确认)。
            红线:全程虚拟资金 · 复用 place_market_order 虚拟撮合 · 绝不接真实交易通道。 */}
        <aside className="w-full shrink-0 space-y-4 lg:w-[360px]">
          <AiDecisionCard symbol={symbol} market={market} period={period} />
          <SpotOrderPanel symbol={symbol} name={name} market={market} />
          {/* 本币条件单(ADR 0041 刀3)· 共享列表 · 30s 轮询 · 有单才显示 */}
          <ConditionalOrdersList symbol={symbol} market={market} />
        </aside>
      </div>
    </main>
  )
}
