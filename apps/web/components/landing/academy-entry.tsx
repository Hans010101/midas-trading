/**
 * 官网区块 · 交易训练营入口卡片(教学内容 · 同 /lab 触达方式 —— 隐藏路由 + landing 入口,
 * 暂不进全局导航)。引导按钮跳 /academy。风格与现有 landing 卡片一致。
 */

import { ArrowRight, GraduationCap } from 'lucide-react'
import Link from 'next/link'

export function AcademyEntry() {
  return (
    <section id="academy" className="mx-auto max-w-6xl px-6 py-20">
      <div className="rounded-2xl border border-paper bg-cream p-8 shadow-md lg:p-12">
        <div className="flex flex-col items-start gap-6 lg:flex-row lg:items-center lg:justify-between">
          <div className="max-w-2xl">
            <p className="mb-2 flex items-center gap-2 text-xs uppercase tracking-[0.3em] text-gold">
              <GraduationCap className="h-4 w-4" />
              交易训练营
            </p>
            <h2 className="font-serif text-3xl font-bold leading-snug lg:text-4xl">
              从入门到缠论、合约的系统教程
            </h2>
            <p className="mt-4 text-sm leading-relaxed text-muted-foreground lg:text-base">
              K 线怎么读、做多与做空、杠杆、均线 / MACD / 布林带、缠论结构……
              由浅入深的免费图文课程,配 66 条名词词典随手查。新手也能一步步看懂市场。
            </p>
            <p className="mt-3 text-xs text-muted-foreground/60">
              教学内容,仅供学习参考,不构成投资建议。
            </p>
          </div>
          <Link
            href="/academy"
            className="inline-flex shrink-0 items-center gap-2 rounded-md bg-midas-red px-6 py-3 text-sm font-medium text-white shadow-sm transition-colors hover:bg-midas-red-deep"
          >
            进入训练营
            <ArrowRight className="h-4 w-4" />
          </Link>
        </div>
      </div>
    </section>
  )
}
