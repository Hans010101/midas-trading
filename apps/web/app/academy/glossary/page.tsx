/**
 * 名词词典页 · server component(fs 读 glossary.md → ArticleRenderer 渲染)。
 *
 * 词典本身是结构化 markdown(含目录 + 10 大类 + 88 条 · 每条一句话定义 + 展开 + 关联词条),
 * 直接整篇渲染即可(目录里的锚点跳转随 md 渲染天然生效)。全免费,无门控。
 *
 * UI 修补:删二级标签行,改为常驻左侧导航 AcademySideNav(active='glossary' · 词典项高亮)。
 */

import type { Metadata } from 'next'
import { cookies } from 'next/headers'

import { AcademyGlossaryContent } from '@/components/academy/academy-glossary-content'
import { HashScroller } from '@/components/academy/hash-scroller'
import { TopNav } from '@/components/layout/top-nav'
import { LOCALE_COOKIE } from '@/i18n/routing'
import { JsonLd } from '@/components/seo/json-ld'
import { getGlossary } from '@/lib/academy'
import { buildGlossaryTermSet } from '@/lib/academy/glossary-schema'

// SEO 批3:词典独立 metadata + DefinedTermSet JSON-LD(88 词条喂 AI 引擎抽取)。
export async function generateMetadata(): Promise<Metadata> {
  const locale = (await cookies()).get(LOCALE_COOKIE)?.value === 'en' ? 'en' : 'zh'
  const english = locale === 'en'
  const title = english
    ? 'Trading Glossary · 88 Essential Terms'
    : '交易名词词典 · 88 条速查'
  const description = english
    ? 'A practical reference to 88 essential trading terms across market basics, order execution, derivatives, technical analysis, Chan Theory, strategy and risk.'
    : '88 个交易名词速查 · 10 大类:基础概念、订单交易、合约衍生品、技术指标、缠论、策略与风险等,每条一句话定义 + 展开说明。'

  return {
    title: {
      absolute: english ? `${title} · Midas Trading` : `${title} · 点金 Midas`,
    },
    description,
    alternates: {
      canonical: '/academy/glossary',
      languages: {
        'zh-CN': '/academy/glossary',
        en: '/en/academy/glossary',
        'x-default': '/academy/glossary',
      },
    },
    openGraph: {
      title: english ? `${title} · Midas Trading` : `${title} · 点金 Midas`,
      description: english
        ? '88 essential trading terms, organized into 10 categories with concise definitions and expanded explanations.'
        : '88 个交易名词 · 10 大类 · 一句话定义 + 展开。',
      url: '/academy/glossary',
    },
  }
}

export default function AcademyGlossaryPage() {
  const markdown = getGlossary()
  const markdownEn = getGlossary('en')

  return (
    <div className="flex min-h-screen flex-col bg-background text-foreground">
      <JsonLd data={buildGlossaryTermSet()} />
      <TopNav />
      {/* 到达 /academy/glossary#<术语id> 时滚动定位到对应词条(软导航/直接访问都兜底)*/}
      <HashScroller />
      <main className="flex-1">
        <div className="mx-auto max-w-5xl px-6 py-6">
          <AcademyGlossaryContent markdownZh={markdown} markdownEn={markdownEn} />
        </div>
      </main>
    </div>
  )
}
