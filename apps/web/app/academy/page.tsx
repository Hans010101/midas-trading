/**
 * 训练营首页 · 列表页(server component · 无 hooks · 全免费无门控)。
 *
 * TopNav + AcademyNav + 简介/免责 + 五阶概览卡片(当前 basics/technical/chan 三阶有内容)+
 * 词典入口卡片。阶卡点击 → /academy/stage?s={slug};词典 → /academy/glossary。
 * ⛔ 不用 [id] 动态段;入口走查询参数(项目零先例规矩)。
 */

import { ArrowRight, BookOpen, GraduationCap } from 'lucide-react'
import Link from 'next/link'

import { AcademyNav } from '@/components/academy/academy-nav'
import { TopNav } from '@/components/layout/top-nav'
import { ACADEMY_ARTICLES, ACADEMY_STAGES } from '@/content/academy/manifest'

export default function AcademyHomePage() {
  return (
    <div className="flex min-h-screen flex-col bg-background text-foreground">
      <TopNav />
      <main className="flex-1">
        <div className="mx-auto max-w-5xl px-6 py-6">
          <AcademyNav />

          {/* 简介 + 免责 */}
          <header className="mb-8">
            <h1 className="flex items-center gap-2 font-serif text-2xl font-bold lg:text-3xl">
              <GraduationCap className="h-7 w-7 text-midas-red" />
              交易训练营
            </h1>
            <p className="mt-3 max-w-2xl text-sm leading-relaxed text-muted-foreground">
              从 K 线、杠杆到缠论结构,由浅入深、配图讲解,新手也能一步步看懂市场。
            </p>
          </header>

          {/* 五阶概览(目前 3 阶有内容)*/}
          <div className="grid gap-4 sm:grid-cols-2">
            {ACADEMY_STAGES.map((stage) => {
              const count = ACADEMY_ARTICLES.filter((a) => a.stage === stage.slug).length
              return (
                <Link
                  key={stage.slug}
                  href={`/academy/stage?s=${stage.slug}`}
                  className="group flex flex-col rounded-xl border border-paper bg-cream p-5 shadow-sm transition-colors hover:border-midas-red/40"
                >
                  <div className="flex items-center justify-between">
                    <span className="rounded-full bg-midas-red/10 px-2.5 py-0.5 font-mono text-xs text-midas-red">
                      {stage.stageLabel}
                    </span>
                    <span className="text-xs text-muted-foreground/70">共 {count} 篇</span>
                  </div>
                  <h2 className="mt-3 font-serif text-lg font-bold">{stage.name}</h2>
                  <p className="mt-2 flex-1 text-sm leading-relaxed text-muted-foreground">
                    {stage.desc}
                  </p>
                  <span className="mt-4 inline-flex items-center gap-1 text-sm font-medium text-midas-red">
                    开始学习
                    <ArrowRight className="h-4 w-4 transition-transform group-hover:translate-x-0.5" />
                  </span>
                </Link>
              )
            })}
          </div>

          {/* 词典入口 */}
          <Link
            href="/academy/glossary"
            className="mt-4 flex items-center gap-4 rounded-xl border border-paper bg-surface-subtle p-5 shadow-sm transition-colors hover:border-gold/50"
          >
            <BookOpen className="h-8 w-8 shrink-0 text-gold" />
            <div className="min-w-0 flex-1">
              <h2 className="font-serif text-lg font-bold">名词词典</h2>
              <p className="mt-1 text-sm text-muted-foreground">
                66 个交易名词速查 · 8 大类 · 一句话定义 + 展开说明
              </p>
            </div>
            <ArrowRight className="h-5 w-5 shrink-0 text-muted-foreground/50" />
          </Link>
        </div>
      </main>
    </div>
  )
}
