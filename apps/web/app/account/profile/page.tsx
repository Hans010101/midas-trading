'use client'

/**
 * 账号与偏好(用户中心模块④ · 重组刀2 实装)。
 *
 * 装配(组件内部零改动):
 *   ① 账户基本信息(邮箱 + 用户 ID · 从 /account 区块1 搬入,身份信息归④)
 *   ② 涨跌色偏好 + ③ Bot 下单预设(从 /settings 搬入 · 零 props 自包含)
 *   ④ 安全设置占位(M1 待实装)
 */

import { useSession } from 'next-auth/react'

import { QuotaCard } from '@/components/account/quota-card'
import { RedeemCard } from '@/components/account/redeem-card'
import { BotOrderPresetSection } from '@/components/settings/bot-order-preset-section'
import { ColorPrefSection } from '@/components/settings/color-pref-section'

export default function ProfilePage() {
  const { data: session } = useSession()

  return (
    <div>
      <h1 className="mb-6 font-serif text-2xl font-bold text-foreground">账号与偏好</h1>

      {/* ① 账户基本信息(原 /account 区块1 原样搬入) */}
      <section className="mb-10">
        <h2 className="mb-3 font-serif text-xl font-bold text-foreground">
          账户基本信息
        </h2>
        <div className="rounded-lg border border-paper bg-cream p-5 shadow-sm">
          <dl className="space-y-2 text-sm">
            <div className="flex justify-between">
              <dt className="text-muted-foreground">邮箱</dt>
              <dd className="font-mono text-foreground">
                {session?.user?.email ?? '—'}
              </dd>
            </div>
            <div className="flex justify-between">
              <dt className="text-muted-foreground">用户 ID</dt>
              <dd className="font-mono text-xs text-muted-foreground/70">
                {session?.user?.id ?? '—'}
              </dd>
            </div>
          </dl>
        </div>
      </section>

      {/* ①.5 我的额度(会员刀2:方案 + 沙盘/回测用量 + 重置口径) */}
      <QuotaCard />

      {/* ①.6 兑换码(兑换码刀2:输入码开/续 Pro · 成功即时刷新额度卡) */}
      <RedeemCard />

      {/* ② 涨跌色偏好 + ③ Bot 下单预设(/settings 搬入) */}
      <ColorPrefSection />
      <BotOrderPresetSection />

      {/* ④ 安全设置占位(M1) */}
      <section className="mb-6 rounded-lg border border-dashed border-paper bg-surface-card p-5">
        <div className="mb-2 flex items-center gap-2">
          <h2 className="font-serif text-lg font-bold text-muted-foreground/70">安全设置</h2>
          <span className="rounded bg-paper px-1.5 py-0.5 font-mono text-[10px] text-muted-foreground">
            M1 待实装
          </span>
        </div>
        <p className="text-xs text-muted-foreground/70">
          密码修改 · 2FA · 登录设备管理 · 操作日志
        </p>
      </section>
    </div>
  )
}
