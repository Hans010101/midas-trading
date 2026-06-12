'use client'

/**
 * /account · 资产总览(用户中心模块① · 重组刀3 瘦身后)。
 *
 * 只留资产视角:虚拟资金管理(激活/重置)+ KPI 卡 + 权益曲线。
 * 持仓/订单/条件单已搬模块②(/account/positions)· 身份信息在模块④(profile)。
 * TopNav / main 容器由 app/account/layout.tsx 提供。
 */

import { AccountOverview } from '@/components/account/account-overview'
import { WalletSection } from '@/components/account/wallet-section'

export default function AccountPage() {
  return (
    <>
      <div className="mb-6 flex items-center gap-3">
        <h1 className="font-serif text-2xl font-bold text-foreground">
          资产总览
        </h1>
      </div>

      {/* 账户资金设置(激活 / 重置)*/}
      <WalletSection />

      {/* KPI 卡 + 权益曲线 */}
      <AccountOverview />
    </>
  )
}
