/**
 * 港股个股详情页 · /hk-preview?symbol=00700(港股阶段二 · 单元2)。
 *
 * 复用 SpotDetail(market="hk")· 与 cn-preview / us-preview 同构(3 行壳 + Suspense)。
 * ★ 港股阶段三全开:K线 + 缠论 + 指标 + AI 决策卡(单元1)+ 形态A 策略信号(单元2)+ 虚拟下单(单元3)。
 *   下单区:按手 board lot 取整 + 印花税 0.1%+佣金 0.1% + 二次确认 · 复用 place_market_order 虚拟撮合。
 * middleware 不保护看图路径 · 匿名可看 K线 / 缠论 / 策略 · 下单需登录 + 激活港股虚拟账户。
 *
 * 红线:点金永远只用虚拟资金 · 绝不接真实交易通道(港股下单复用现有虚拟引擎,与 A股/美股同口径)。
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
