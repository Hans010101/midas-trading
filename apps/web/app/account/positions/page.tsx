import { Suspense } from 'react'

import { PositionsHub } from '@/components/account/positions-hub'

/**
 * 持仓与订单(用户中心模块② · 重组刀3 实装)。
 * 两层结构(同 cn-preview 范式):page 只包 Suspense 边界(PositionsHub 用 useSearchParams)。
 */
export default function PositionsPage() {
  return (
    <Suspense fallback={<p className="py-12 text-center text-muted-foreground">载入中…</p>}>
      <PositionsHub />
    </Suspense>
  )
}
