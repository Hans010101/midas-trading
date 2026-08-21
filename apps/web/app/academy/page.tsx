/**
 * 训练营首页 · 列表页(server component · 无 hooks · 全免费无门控)。
 *
 * TopNav + 五阶概览卡片 + ★各阶文章速览(SEO 批2:server 渲染文章 <a> 入口 · 打通「首页→文章」
 * 纯 HTML 爬行链 · 修 118 篇爬虫孤岛)+ 词典入口卡片。
 * 阶卡点击 → /academy/stage/{slug};文章 → /academy/article/{slug}(路径段 · docs/decisions/0045)。
 * 左侧导航只在内页(列表/详情/词典),首页不挂。
 */

import type { Metadata } from 'next'
import { AcademyHomeContent } from '@/components/academy/academy-home-content'
import { TopNav } from '@/components/layout/top-nav'

// SEO 批3:训练营首页独立 metadata(此前吃全站模板)。
export const metadata: Metadata = {
  title: '交易训练营 · 118 篇免费教学',
  description:
    '免费系统化交易教学:K线、做多做空、杠杆、技术指标、缠论、永续合约到交易体系六阶 118 篇图文文章,配 88 条名词词典。',
  alternates: {
    canonical: '/academy',
    languages: { 'zh-CN': '/academy', en: '/en/academy', 'x-default': '/academy' },
  },
  openGraph: {
    title: '交易训练营 · 118 篇免费教学 · 点金 Midas',
    description: '六阶系统教学 118 篇 + 88 条名词词典,从 K 线到缠论、合约。',
    url: '/academy',
  },
}

export default function AcademyHomePage() {
  return (
    <div className="flex min-h-screen flex-col bg-background text-foreground">
      <TopNav />
      <main className="flex-1">
        <AcademyHomeContent />
      </main>
    </div>
  )
}
