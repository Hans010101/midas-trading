import Link from 'next/link'

/**
 * 持仓与订单(用户中心模块② · 刀1 占位)。
 * 内容搬迁是刀3:spot/perp 当前持仓 + 历史持仓 + 订单流水 + 条件单(页内 tab)。
 */
export default function PositionsPage() {
  return (
    <div>
      <h1 className="mb-4 font-serif text-2xl font-bold text-foreground">持仓与订单</h1>
      <div className="rounded-lg border border-dashed border-paper bg-surface-card p-6">
        <p className="text-sm leading-relaxed text-muted-foreground">
          内容迁移中(重组刀3)· 当前持仓 / 历史持仓 / 订单流水 / 条件单暂在{' '}
          <Link href="/account" className="text-midas-red hover:underline">
            资产总览
          </Link>{' '}
          页下半部分,功能完整可用。
        </p>
      </div>
    </div>
  )
}
