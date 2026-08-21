import type { Metadata } from 'next'
import Link from 'next/link'

import { PublicProse, PublicSiteShell } from '@/components/seo/public-site-shell'

export const metadata: Metadata = {
  title: '研究方法与数据透明度',
  description: 'Midas Trading 的数据来源、更新时间、指标计算、AI 使用、内容审核与修正机制。',
  alternates: {
    canonical: '/research/methodology',
    languages: { 'zh-CN': '/research/methodology', en: '/en/research/methodology', 'x-default': '/research/methodology' },
  },
  openGraph: { title: '研究方法与数据透明度 · Midas Trading', url: '/research/methodology' },
}

export default function MethodologyPage() {
  return (
    <PublicSiteShell>
      <PublicProse>
        <h1 className="font-serif text-3xl font-bold">研究方法与数据透明度</h1>
        <p>本页说明 Midas Trading 如何处理行情、指标、AI 分析与教学内容，方便用户和检索系统判断信息的来源、时效与边界。</p>
        <h2 className="pt-4 font-serif text-xl font-bold">数据层</h2>
        <p>市场页面优先使用交易所、指数与公开市场接口，并按市场分别提供价格、成交量、资金费率、持仓量、多空比等可获得字段。页面展示的更新时间与数据源口径优先于 AI 文字描述；上游暂缺的数据明确显示为空，不用估算值补齐。</p>
        <h2 className="pt-4 font-serif text-xl font-bold">计算层</h2>
        <p>MA、MACD、RSI、布林带、回测收益与缠论结构等结果由确定性规则计算。策略回测使用已完成的历史区间，不把未来数据带入过去，也不把一次回测结果包装为未来表现。</p>
        <h2 className="pt-4 font-serif text-xl font-bold">AI 层</h2>
        <p>AI 用于归纳数据、解释结构和生成自然语言摘要，不负责改写原始行情。生成内容必须能回到可见数据、规则或公开来源；当模型服务不可用时，系统保留规则输出而不是编造结论。</p>
        <h2 className="pt-4 font-serif text-xl font-bold">内容与修正</h2>
        <p>训练营文章由 Midas Trading 研究团队按课程结构维护。文章日期来自版本记录；没有可靠日期时不伪造。发现事实、翻译或数据口径错误后，会在源内容修正并重新发布。</p>
        <h2 className="pt-4 font-serif text-xl font-bold">进一步核验</h2>
        <p>查看<Link href="/research/team" className="mx-1 text-midas-red hover:underline">研究团队</Link>了解署名与编辑责任；产品定位与原则见<Link href="/about" className="mx-1 text-midas-red hover:underline">关于 Midas Trading</Link>。</p>
      </PublicProse>
    </PublicSiteShell>
  )
}
