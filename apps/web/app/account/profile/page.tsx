import Link from 'next/link'

/**
 * 账号与偏好(用户中心模块④ · 刀1 占位)。
 * 内容搬迁是刀2:邮箱/用户 ID + 涨跌色偏好 + Bot 下单预设 + 安全占位。
 */
export default function ProfilePage() {
  return (
    <div>
      <h1 className="mb-4 font-serif text-2xl font-bold text-foreground">账号与偏好</h1>
      <div className="rounded-lg border border-dashed border-paper bg-surface-card p-6">
        <p className="text-sm leading-relaxed text-muted-foreground">
          内容迁移中(重组刀2)· 账号信息暂在{' '}
          <Link href="/account" className="text-midas-red hover:underline">
            资产总览
          </Link>{' '}
          页顶部;涨跌色 / Bot 下单预设暂在{' '}
          <Link href="/settings" className="text-midas-red hover:underline">
            设置
          </Link>{' '}
          页,功能完整可用。
        </p>
      </div>
    </div>
  )
}
