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

const DEFAULTS: Record<'cn' | 'us' | 'hk', { symbol: string; name: string }> = {
  cn: { symbol: '600519', name: '贵州茅台' },
  us: { symbol: 'NVDA', name: 'NVIDIA' },
  hk: { symbol: '00700', name: '腾讯控股' },
}

interface SpotDetailProps {
  // 港股阶段二:hk 复用现货详情页,但 market==='hk' 时 gate 掉 AI 决策卡 + 下单区(见 aside)
  market: 'cn' | 'us' | 'hk'
}

export function SpotDetail({ market }: SpotDetailProps) {
  const searchParams = useSearchParams()
  const { symbol, name } = useMemo(() => {
    const raw = (searchParams.get('symbol') ?? '').trim()
    if (!raw) return DEFAULTS[market]
    return { symbol: raw.toUpperCase(), name: (searchParams.get('name') ?? '').trim() }
  }, [searchParams, market])
  // 默认周期:cn/us 用 1h(日内 · 15m/1h/1d 可切);★港股只支持日/周线(hk_source 无分钟线)→ 默认且仅 1d
  const [period, setPeriod] = useState<Period>(market === 'hk' ? '1d' : '1h')

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

        {/* 右侧栏:AI 决策卡(复用工作台)+ 下单区(差异化)
            ★ 港股阶段二完全不渲染整块 aside(拍板②:不显示「即将上线」占位、无噪音):
              · decision-card?market=hk 后端 technical agent prompt 无 hk 键 → 会 500(港股不接 AI)
              · 港股下单是阶段三(每手 board lot 逻辑)· 阶段二不可交易
            market!=='hk' 内 market 收窄为 'cn'|'us',AiDecisionCard / SpotOrderPanel 类型无需改。 */}
        {market !== 'hk' && (
          <aside className="w-full shrink-0 space-y-4 lg:w-[360px]">
            <AiDecisionCard symbol={symbol} market={market} period={period} />
            <SpotOrderPanel symbol={symbol} name={name} market={market} />
          </aside>
        )}
      </div>
    </main>
  )
}
