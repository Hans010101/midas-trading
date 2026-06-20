'use client'

import dynamic from 'next/dynamic'
import { type ComponentType } from 'react'

import { type InteractiveKey } from '@/content/academy/interactives'

/**
 * key → 交互组件 注册表。next/dynamic 懒加载(默认 ssr:true · 组件可正常服务端渲染),
 * 每篇文章只下载它用到的那 0–N 个组件 JS,不把全部 D 组件打进共用的文章路由包。
 * 逐批扩展:实现新组件后,在此加一行 dynamic,并在 interactives.ts 的 IMPLEMENTED_KEYS 追加。
 *
 * Partial<Record<...>>:只列已实现 key;未实现 key 不会被 ACADEMY_INTERACTIVES 引用
 * (由 interactives.test.ts 的「只能映射到已实现组件」单测兜底)。
 */
const REGISTRY: Partial<Record<InteractiveKey, ComponentType>> = {
  // 第一批
  liquidation: dynamic(() => import('./liquidation-demo').then((m) => m.LiquidationDemo)),
  'chan-pivot': dynamic(() => import('./chan-pivot-demo').then((m) => m.ChanPivotDemo)),
  kline: dynamic(() => import('./kline-anatomy-demo').then((m) => m.KlineAnatomyDemo)),
  // 第二批:合约与风控
  'funding-rate': dynamic(() => import('./funding-rate-demo').then((m) => m.FundingRateDemo)),
  'position-sizing': dynamic(() => import('./position-sizing-demo').then((m) => m.PositionSizingDemo)),
  'margin-mode': dynamic(() => import('./margin-mode-demo').then((m) => m.MarginModeDemo)),
  'pnl-exposure': dynamic(() => import('./pnl-exposure-demo').then((m) => m.PnlExposureDemo)),
  'liquidation-process': dynamic(() => import('./liquidation-process-demo').then((m) => m.LiquidationProcessDemo)),
  // 第三批:技术指标
  'moving-average': dynamic(() => import('./moving-average-demo').then((m) => m.MovingAverageDemo)),
  macd: dynamic(() => import('./macd-demo').then((m) => m.MacdDemo)),
  bollinger: dynamic(() => import('./bollinger-demo').then((m) => m.BollingerDemo)),
  rsi: dynamic(() => import('./rsi-demo').then((m) => m.RsiDemo)),
}

export function ArticleInteractives({ keys }: { keys: InteractiveKey[] }) {
  if (!keys || keys.length === 0) return null
  return (
    <section className="mt-8">
      {keys.map((k) => {
        const Comp = REGISTRY[k]
        return Comp ? <Comp key={k} /> : null
      })}
    </section>
  )
}
