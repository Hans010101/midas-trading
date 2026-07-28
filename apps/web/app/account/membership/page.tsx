'use client'

/** 个人中心。历史路由保留兼容，商业会员相关组件暂不渲染。 */

import { AccountIdentitySection } from '@/components/account/account-identity-section'

export default function AccountHubPage() {
  return (
    <div>
      <h1 className="mb-6 font-serif text-2xl font-bold text-foreground">个人中心</h1>

      {/* ① 账户身份:头像(+ 选择器)+ 邮箱/ID + 修改密码 */}
      <AccountIdentitySection />

    </div>
  )
}
