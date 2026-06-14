'use client'

/**
 * 会员(用户中心模块 · Phase 2a 刀2)· 支持者计划定价 + 订阅支付流程。
 * TopNav / main 容器由 app/account/layout.tsx 提供。
 */

import { MembershipSection } from '@/components/account/membership-section'

export default function MembershipPage() {
  return (
    <>
      <h1 className="mb-6 font-serif text-2xl font-bold text-foreground">会员</h1>
      <MembershipSection />
    </>
  )
}
