/**
 * 名词词典页 · server component(fs 读 glossary.md → ArticleRenderer 渲染)。
 *
 * 词典本身是结构化 markdown(含目录 + 10 大类 + 88 条 · 每条一句话定义 + 展开 + 关联词条),
 * 直接整篇渲染即可(目录里的锚点跳转随 md 渲染天然生效)。全免费,无门控。
 *
 * UI 修补:删二级标签行,改为常驻左侧导航 AcademySideNav(active='glossary' · 词典项高亮)。
 */

import type { Metadata } from 'next'

import { AcademySideNav } from '@/components/academy/academy-side-nav'
import { ArticleRenderer } from '@/components/academy/article-renderer'
import { HashScroller } from '@/components/academy/hash-scroller'
import { TopNav } from '@/components/layout/top-nav'
import { JsonLd } from '@/components/seo/json-ld'
import { getGlossary } from '@/lib/academy'
import { buildGlossaryTermSet } from '@/lib/academy/glossary-schema'

// SEO 批3:词典独立 metadata + DefinedTermSet JSON-LD(88 词条喂 AI 引擎抽取)。
export const metadata: Metadata = {
  title: '交易名词词典 · 88 条速查',
  description:
    '88 个交易名词速查 · 10 大类:基础概念、订单交易、合约衍生品、技术指标、缠论、策略与风险等,每条一句话定义 + 展开说明。知识科普,不构成投资建议。',
  alternates: { canonical: '/academy/glossary' },
  openGraph: {
    title: '交易名词词典 · 88 条速查 · 点金 Midas',
    description: '88 个交易名词 · 10 大类 · 一句话定义 + 展开。知识科普,不构成投资建议。',
    url: '/academy/glossary',
  },
}

export default function AcademyGlossaryPage() {
  const markdown = getGlossary()

  return (
    <div className="flex min-h-screen flex-col bg-background text-foreground">
      <JsonLd data={buildGlossaryTermSet()} />
      <TopNav />
      {/* 到达 /academy/glossary#<术语id> 时滚动定位到对应词条(软导航/直接访问都兜底)*/}
      <HashScroller />
      <main className="flex-1">
        <div className="mx-auto max-w-5xl px-6 py-6">
          <div className="lg:flex lg:gap-8">
            <AcademySideNav active="glossary" />
            <div className="min-w-0 flex-1">
              <ArticleRenderer markdown={markdown} />
              <p className="mt-8 border-t border-paper pt-4 text-xs text-muted-foreground/60">
                教学内容,仅供学习参考,不构成投资建议。
              </p>
            </div>
          </div>
        </div>
      </main>
    </div>
  )
}
