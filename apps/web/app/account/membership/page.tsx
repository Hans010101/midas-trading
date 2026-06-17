'use client'

/**
 * 个人中心(账户重组)· 账户身份 + 会员/额度 + 套餐升级 + 兑换码 + 安全设置一站式。
 *
 * ★ 路由保持 /account/membership 不变(付费墙「开通 Pro」跳此 · 改路由会断链)· 只改标题 + 内容构成。
 * 组件内部零改动:QuotaCard / MembershipSection / RedeemCard 自包含(各自管数据请求)。
 * 顺序:账户身份 → 额度 → 套餐升级(含客服)→ 兑换码 → 安全设置。
 */

import { useSession } from 'next-auth/react'

import { MembershipSection } from '@/components/account/membership-section'
import { QuotaCard } from '@/components/account/quota-card'
import { RedeemCard } from '@/components/account/redeem-card'

export default function AccountHubPage() {
  const { data: session } = useSession()

  return (
    <div>
      <h1 className="mb-6 font-serif text-2xl font-bold text-foreground">个人中心</h1>

      {/* ① 账户基本信息(原 /account/profile 搬入) */}
      <section className="mb-10">
        <h2 className="mb-3 font-serif text-xl font-bold text-foreground">账户基本信息</h2>
        <div className="rounded-lg border border-paper bg-cream p-5 shadow-sm">
          <dl className="space-y-2 text-sm">
            <div className="flex justify-between">
              <dt className="text-muted-foreground">邮箱</dt>
              <dd className="font-mono text-foreground">{session?.user?.email ?? '—'}</dd>
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

      {/* ② 我的会员状态 + 额度(方案 + 沙盘/回测用量 + 重置)*/}
      <QuotaCard />

      {/* ③ 套餐升级 + 客服入口(MembershipSection 含联系客服)*/}
      <MembershipSection />

      {/* ④ 兑换码(输入码开/续 Pro · 成功即时刷新额度卡)*/}
      <RedeemCard />

      {/* ⑤ 安全设置占位(M1 · 账户安全归个人中心)*/}
      <section className="mb-6 mt-6 rounded-lg border border-dashed border-paper bg-surface-card p-5">
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
