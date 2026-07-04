'use client'

/**
 * 个人中心(账户重组)· 账户身份(头像+邮箱+改密码)+ 会员/额度 + 套餐升级(含兑换码 + 客服)。
 *
 * ★ 路由保持 /account/membership 不变(付费墙「开通 Pro」跳此 · 改路由会断链)· 只改标题 + 内容构成。
 * 兑换码已并入 MembershipSection 套餐排第 4 框(不再单独 RedeemCard)。
 */

import { AccountIdentitySection } from '@/components/account/account-identity-section'
import { MembershipSection } from '@/components/account/membership-section'
import { QuotaCard } from '@/components/account/quota-card'

export default function AccountHubPage() {
  return (
    <div>
      <h1 className="mb-6 font-serif text-2xl font-bold text-foreground">个人中心</h1>

      {/* ① 账户身份:头像(+ 选择器)+ 邮箱/ID + 修改密码 */}
      <AccountIdentitySection />

      {/* ② 我的会员状态 + 额度(方案 + 沙盘/回测用量)*/}
      <QuotaCard />

      {/* ③ 套餐升级 + 兑换码(第 4 框)+ 客服入口 */}
      <MembershipSection />
    </div>
  )
}
