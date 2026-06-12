import Link from 'next/link'

/**
 * 通知与提醒(用户中心模块③ · 刀1 占位)。
 * 内容搬迁是刀2:TG/飞书绑定 + 事件开关 + 免打扰 + 价格预警规则。
 */
export default function AlertsPage() {
  return (
    <div>
      <h1 className="mb-4 font-serif text-2xl font-bold text-foreground">通知与提醒</h1>
      <div className="rounded-lg border border-dashed border-paper bg-surface-card p-6">
        <p className="text-sm leading-relaxed text-muted-foreground">
          内容迁移中(重组刀2)· 推送绑定 / 事件开关 / 免打扰 / 价格预警暂在{' '}
          <Link href="/settings" className="text-midas-red hover:underline">
            设置
          </Link>{' '}
          页,功能完整可用。
        </p>
      </div>
    </div>
  )
}
