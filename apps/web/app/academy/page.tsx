/**
 * 训练营首页 · 列表页(server component · 无 hooks · 全免费无门控)。
 *
 * TopNav + 五阶概览卡片 + ★各阶文章速览(SEO 批2:server 渲染文章 <a> 入口 · 打通「首页→文章」
 * 纯 HTML 爬行链 · 修 118 篇爬虫孤岛)+ 词典入口卡片。
 * 阶卡点击 → /academy/stage/{slug};文章 → /academy/article/{slug}(路径段 · docs/decisions/0045)。
 * 左侧导航只在内页(列表/详情/词典),首页不挂。
 */

import type { Metadata } from 'next'
import { ArrowRight, BookOpen } from 'lucide-react'
import Link from 'next/link'

import { StageGraduatedBadge } from '@/components/academy/stage-graduated-badge'
import { StageProgress } from '@/components/academy/stage-progress'
import { TopNav } from '@/components/layout/top-nav'
import { ACADEMY_ARTICLES, ACADEMY_STAGES } from '@/content/academy/manifest'

// SEO 批3:训练营首页独立 metadata(此前吃全站模板)。
export const metadata: Metadata = {
  title: '交易训练营 · 118 篇免费教学',
  description:
    '免费系统化交易教学:K线、做多做空、杠杆、技术指标、缠论、永续合约到交易体系六阶 118 篇图文文章,配 88 条名词词典。',
  alternates: { canonical: '/academy' },
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
        <div className="mx-auto max-w-5xl px-6 py-6">
          {/* 五阶概览 */}
          <div className="grid gap-4 sm:grid-cols-2">
            {ACADEMY_STAGES.map((stage) => {
              const count = ACADEMY_ARTICLES.filter((a) => a.stage === stage.slug).length
              return (
                <Link
                  key={stage.slug}
                  href={`/academy/stage/${stage.slug}`}
                  className="group flex flex-col rounded-xl border border-paper bg-cream p-5 shadow-sm transition-colors hover:border-midas-red/40"
                >
                  <div className="flex items-center justify-between">
                    <span className="rounded-full bg-midas-red/10 px-2.5 py-0.5 font-mono text-xs text-midas-red">
                      {stage.stageLabel}
                    </span>
                    <div className="flex items-center gap-2">
                      {/* 结业徽章(已结业才显 · B 期刀2)*/}
                      <StageGraduatedBadge stageSlug={stage.slug} />
                      <span className="text-xs text-muted-foreground/70">共 {count} 篇</span>
                    </div>
                  </div>
                  <h2 className="mt-3 font-serif text-lg font-bold">{stage.name}</h2>
                  <p className="mt-2 flex-1 text-sm leading-relaxed text-muted-foreground">
                    {stage.desc}
                  </p>
                  {/* 学习进度(登录后显示已学 X/Y · 分母=有小测文章数 · B 期刀1.5)*/}
                  <StageProgress stageSlug={stage.slug} className="mt-4" />
                  <span className="mt-4 inline-flex items-center gap-1 text-sm font-medium text-midas-red">
                    开始学习
                    <ArrowRight className="h-4 w-4 transition-transform group-hover:translate-x-0.5" />
                  </span>
                </Link>
              )
            })}
          </div>

          {/* ★各阶文章速览(SEO 批2)· server 渲染 <a> 入口:打通「首页→文章」纯 HTML 爬行链
              (此前文章链接只在 client 渲染的阶列表里 · 非 JS 爬虫发现不了任何一篇 · 审计 critical)*/}
          <section className="mt-8">
            <h2 className="mb-4 font-serif text-lg font-bold">从这里开始读</h2>
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {ACADEMY_STAGES.map((stage) => {
                const top3 = ACADEMY_ARTICLES.filter((a) => a.stage === stage.slug)
                  .sort((a, b) => a.order - b.order)
                  .slice(0, 3)
                return (
                  <div key={stage.slug} className="rounded-xl border border-paper bg-cream p-4 shadow-sm">
                    <p className="mb-2 font-mono text-xs text-midas-red">{stage.stageLabel} · {stage.name}</p>
                    <ul className="space-y-1.5">
                      {top3.map((a) => (
                        <li key={a.slug}>
                          <Link
                            href={`/academy/article/${a.slug}`}
                            className="line-clamp-1 text-sm text-foreground/80 transition-colors hover:text-midas-red"
                          >
                            {a.title}
                          </Link>
                        </li>
                      ))}
                    </ul>
                  </div>
                )
              })}
            </div>
          </section>

          {/* 词典入口 */}
          <Link
            href="/academy/glossary"
            className="mt-4 flex items-center gap-4 rounded-xl border border-paper bg-surface-subtle p-5 shadow-sm transition-colors hover:border-gold/50"
          >
            <BookOpen className="h-8 w-8 shrink-0 text-gold" />
            <div className="min-w-0 flex-1">
              <h2 className="font-serif text-lg font-bold">名词词典</h2>
              <p className="mt-1 text-sm text-muted-foreground">
                88 个交易名词速查 · 10 大类 · 一句话定义 + 展开说明
              </p>
            </div>
            <ArrowRight className="h-5 w-5 shrink-0 text-muted-foreground/50" />
          </Link>
        </div>
      </main>
    </div>
  )
}
