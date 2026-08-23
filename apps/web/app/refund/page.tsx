import type { Metadata } from 'next'

import { LegalP, LegalPage } from '@/components/legal/legal-page'

export const dynamic = 'force-static'

export const metadata: Metadata = {
  title: '免费服务说明',
  description: 'Midas Trading 当前不提供付费订阅或付费功能。',
  alternates: {
    canonical: '/refund',
    languages: { 'zh-CN': '/refund', en: '/en/refund', 'x-default': '/refund' },
  },
  openGraph: { title: '免费服务说明 · Midas Trading', url: '/refund' },
}

export default function RefundPage() {
  return (
    <LegalPage title="免费服务说明" alternateHref="/en/refund">
      <LegalP>
        Midas Trading 当前不提供付费订阅、自动续费或付费功能。注册并登录后即可免费使用平台已开放功能，因此当前不存在购买或退款流程。
      </LegalP>
      <LegalP>
        如您曾参与历史测试并有相关问题，可通过“联系我们”提交工单处理。
      </LegalP>
    </LegalPage>
  )
}
