/**
 * 官网区块 · 交易训练营入口卡片(教学内容 · 同 /lab 触达方式 —— 隐藏路由 + landing 入口,
 * 暂不进全局导航)。引导按钮跳 /academy。风格与现有 landing 卡片一致。
 *
 * 训练营永久免费开放；完成模块测验仅记录学习进度与结业成绩。
 * ★合规:无稳赚/暴富/保证收益,不暗示学习能盈利;保留教学免责语。
 * ★暗色:全用 token(项目 .dark 预留未切换 · 全站 light-only · 本内联块跟随页面,不自带暗色)。
 */

import { ArrowRight, GraduationCap } from 'lucide-react'
import Link from 'next/link'

// 数字以产品实测为准:6 模块(STAGE_ORDER)· 217 练习题(随堂小测口径)· 88 词典(glossary.md 实测 88 条)
const STATS = [
  { num: '6', label: '大模块' },
  { num: '217', label: '练习题' },
  { num: '88', label: '词典' },
] as const

export function AcademyEntry() {
  return (
    <section id="academy" className="mx-auto max-w-6xl px-6 py-20">
      <div className="rounded-2xl border border-paper bg-cream p-8 shadow-md lg:p-12">
        {/* 顶部:课程介绍(左) + 唯一主 CTA(右)*/}
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
              由浅入深的免费图文课程,从 K 线、做多做空到杠杆、缠论、合约,六大模块带你一步步看懂市场。配
              88 条名词词典,随时查、随时学。
            </p>
            <p className="mt-3 text-xs text-muted-foreground/60">教学内容,仅供学习参考,不构成投资建议。</p>
          </div>

          {/* 唯一主 CTA */}
          <div className="flex shrink-0 flex-col items-start gap-2 lg:items-center">
            <Link
              href="/academy"
              className="inline-flex items-center gap-2 rounded-md bg-midas-red px-6 py-3 text-sm font-medium text-white shadow-sm transition-colors hover:bg-midas-red-deep"
            >
              进入训练营
              <ArrowRight className="h-4 w-4" />
            </Link>
            <p className="text-xs text-muted-foreground/60">免费进入 · 零真金风险</p>
          </div>
        </div>

        {/* 课程规模 */}
        <div className="mt-8 rounded-xl border border-[#F0D9A8] bg-white p-5 shadow-sm dark:border-gold/30 dark:bg-surface-subtle sm:p-6">
          <div className="grid grid-cols-3 gap-3 sm:gap-4">
            {STATS.map((s) => (
              <div key={s.label} className="text-center">
                <div className="font-serif text-2xl font-bold text-gold sm:text-3xl">{s.num}</div>
                <div className="mt-0.5 text-xs text-muted-foreground sm:text-sm">{s.label}</div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </section>
  )
}
