/**
 * 美股个股详情页 · /us-preview?symbol=NVDA(0023 阶段③ · 3.4 批2)。
 *
 * 两层结构(同 crypto-preview):本 page 只包 Suspense 边界(SpotDetail 用 useSearchParams)。
 * 美股详情页右栏下单区支持做多 + 卖空(无杠杆 · 接 3.4 批1 引擎)。
 * middleware 不保护此路径 · 匿名可看 K线/缠论/AI · 下单时组件内引导登录。
 *
 * 红线:点金永远只用虚拟资金 · 美股卖空只是虚拟负持仓记账 · 绝不接真实交易。
 */

import { Suspense } from 'react'

import { CuratedRedirect } from '@/components/seo/curated-redirect'
import { SpotDetail } from '@/components/spot-preview/spot-detail'

export default function UsPreviewPage() {
  return (
    <Suspense fallback={<main className="min-h-screen bg-background" />}>
      <CuratedRedirect market="us" />
      <SpotDetail market="us" />
    </Suspense>
  )
}
