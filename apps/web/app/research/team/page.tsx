import type { Metadata } from 'next'

import { JsonLd } from '@/components/seo/json-ld'
import { PublicProse, PublicSiteShell } from '@/components/seo/public-site-shell'
import { researchTeamSchema } from '@/lib/seo/schema'

export const metadata: Metadata = {
  title: 'Midas Trading 研究团队',
  description: 'Midas Trading 公开内容的组织署名、研究范围与编辑责任。',
  alternates: {
    canonical: '/research/team',
    languages: { 'zh-CN': '/research/team', en: '/en/research/team', 'x-default': '/research/team' },
  },
  openGraph: { title: 'Midas Trading 研究团队', url: '/research/team' },
}

export default function ResearchTeamPage() {
  return (
    <PublicSiteShell>
      <JsonLd data={researchTeamSchema} />
      <PublicProse>
        <h1 className="font-serif text-3xl font-bold">Midas Trading 研究团队</h1>
        <p>这是 Midas Trading 训练营、词典、研究方法与市场解释内容的统一组织署名，不对应虚构的个人专家。</p>
        <h2 className="pt-4 font-serif text-xl font-bold">研究范围</h2>
        <p>团队内容覆盖市场基础、技术指标、缠论结构、永续合约数据、策略回测、交易计划与复盘方法。产品工程负责数据链路和确定性计算，内容维护负责课程结构、事实核验与中英文一致性。</p>
        <h2 className="pt-4 font-serif text-xl font-bold">AI 的角色</h2>
        <p>AI 可参与归纳、翻译与表达优化，但不能替代数据源、公式和编辑责任。公开文章仍以版本记录、可追溯来源与确定性规则为准。</p>
        <h2 className="pt-4 font-serif text-xl font-bold">联系与修正</h2>
        <p>已注册用户可通过站内“支持工单”提交事实、翻译或产品问题；确认后在源内容修正。</p>
      </PublicProse>
    </PublicSiteShell>
  )
}
