/**
 * 港股个股详情页 · /hk-preview?symbol=00700(港股阶段二 · 单元2)。
 *
 * 复用 SpotDetail(market="hk")· 与 cn-preview / us-preview 同构(3 行壳 + Suspense)。
 * ★ 港股阶段三:K线 + 缠论 + 指标 + AI 决策卡(单元1)+ 形态A 策略信号(单元2,纯展示)。
 *   下单区仍 gate(SpotDetail 内 market==='hk' 不渲染 SpotOrderPanel · 留阶段三单元3)。
 * middleware 不保护此路径 · 匿名可看 K线 / 缠论 / 策略信号。
 *
 * 红线:点金永远只用虚拟资金 · 绝不接真实交易通道。港股下单留阶段三单元3(虚拟引擎 + 二次确认)。
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
