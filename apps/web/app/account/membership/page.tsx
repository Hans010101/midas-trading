'use client'

/**
 * 个人中心(账户重组)· 账户身份(头像+邮箱+改密码)+ 会员/额度 + 套餐升级 + 兑换码 一站式。
 *
 * ★ 路由保持 /account/membership 不变(付费墙「开通 Pro」跳此 · 改路由会断链)· 只改标题 + 内容构成。
 * 组件自包含(各自管数据请求)· 顺序:账户身份 → 额度 → 套餐升级(含客服)→ 兑换码。
 */

import { AccountIdentitySection } from '@/components/account/account-identity-section'
import { MembershipSection } from '@/components/account/membership-section'
import { QuotaCard } from '@/components/account/quota-card'
import { RedeemCard } from '@/components/account/redeem-card'

export default function AccountHubPage() {
  return (
    <div>
      <h1 className="mb-6 font-serif text-2xl font-bold text-foreground">个人中心</h1>

      {/* ① 账户身份:头像(+ 选择器)+ 邮箱/ID + 修改密码 */}
      <AccountIdentitySection />

      {/* ② 我的会员状态 + 额度(方案 + 沙盘/回测用量 + 重置)*/}
      <QuotaCard />

      {/* ③ 套餐升级 + 客服入口(MembershipSection 含联系客服)*/}
      <MembershipSection />

      {/* ④ 兑换码(输入码开/续 Pro · 成功即时刷新额度卡)*/}
      <RedeemCard />
    </div>
  )
}
