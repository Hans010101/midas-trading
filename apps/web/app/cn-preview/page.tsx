/**
 * A股个股详情页 · /cn-preview?symbol=600519(0023 阶段③ · 3.4 批2)。
 *
 * 两层结构(同 crypto-preview):本 page 只包 Suspense 边界(SpotDetail 用 useSearchParams)。
 * middleware 不保护此路径 · 匿名可看 K线/缠论/AI · 下单时组件内引导登录。
 *
 * 红线:点金永远只用虚拟资金 · 绝不接真实交易通道。
 */

import { Suspense } from 'react'

import { CuratedRedirect } from '@/components/seo/curated-redirect'
import { SpotDetail } from '@/components/spot-preview/spot-detail'

export default function CnPreviewPage() {
  return (
    <Suspense fallback={<main className="min-h-screen bg-background" />}>
      <CuratedRedirect market="cn" />
      <SpotDetail market="cn" />
    </Suspense>
  )
}
