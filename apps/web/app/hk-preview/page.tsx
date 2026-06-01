/**
 * 港股个股详情页 · /hk-preview?symbol=00700(港股阶段二 · 单元2)。
 *
 * 复用 SpotDetail(market="hk")· 与 cn-preview / us-preview 同构(3 行壳 + Suspense)。
 * ★ 港股阶段二只读:详情页只「看」K线 + 缠论 + 指标 · 不接 AI 决策卡 · 不接下单
 *   (SpotDetail / SpotMainChart 内按 market==='hk' gate 掉 AI 卡 / 下单区 / 形态A策略)。
 * middleware 不保护此路径 · 匿名可看 K线 / 缠论。
 *
 * 红线:点金永远只用虚拟资金 · 绝不接真实交易通道。港股阶段二不可交易(下单留阶段三)。
 */

import { Suspense } from 'react'

import { SpotDetail } from '@/components/spot-preview/spot-detail'

export default function HkPreviewPage() {
  return (
    <Suspense fallback={<main className="min-h-screen bg-background" />}>
      <SpotDetail market="hk" />
    </Suspense>
  )
}
