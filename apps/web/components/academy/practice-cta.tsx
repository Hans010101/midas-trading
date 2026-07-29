'use client'

/**
 * 训练营「去实战练」入口 · 文章末尾的行动卡(server 兼容 · 仅渲染 Next <Link> 软导航)。
 *
 * 由 app/academy/article/page.tsx 按 slug 从 content/academy/practice.ts 取配置 + 拼好的 href 传入;
 * 点击经 Next <Link> 客户端软导航(不整页刷新)跳对应市场详情页
 *   /crypto-preview · /cn-preview · /us-preview · /hk-preview(?symbol=)或 /workbench(无 symbol)。
 *
 * 视觉沿用训练营:中国红强调 / 暖米白底 / Noto Serif 标题。
 * ⛔ 零 [id] 路由 · href 由 buildPracticeHref 拼(走 ?symbol=)。教学页不出现 VIRTUAL 徽章。
 */

import { ArrowUpRight, LineChart } from 'lucide-react'
import Link from 'next/link'

import { useRuntimeLocale } from '@/components/i18n/locale-runtime-provider'
import type { PracticeEntry } from '@/content/academy/practice'

const ENGLISH_LABELS: Record<string, string> = {
  '打开 BTC 行情,对照 K 线的四价与阴阳线':
    'Open BTC and identify each candle’s open, high, low, and close.',
  '在 BTC K 线上找找带长上影 / 长下影的蜡烛':
    'Find BTC candles with long upper or lower wicks.',
  '在贵州茅台日线上叠加均线,观察趋势与金叉死叉':
    'Overlay moving averages on Kweichow Moutai and inspect trend crossovers.',
}

export function PracticeCTA({ entry, href }: { entry: PracticeEntry; href: string }) {
  const { locale } = useRuntimeLocale()
  const en = locale === 'en'
  return (
    <section className="mt-8" aria-label={en ? 'Practice in the terminal' : '去实战练'}>
      <Link
        href={href}
        className="group flex items-center gap-4 rounded-xl border border-midas-red/30 bg-midas-red-glow p-5 shadow-sm transition-colors hover:border-midas-red/60 hover:bg-midas-red-tint"
      >
        <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full bg-midas-red/10 text-midas-red">
          <LineChart className="h-5 w-5" />
        </span>
        <div className="min-w-0 flex-1">
          <span className="font-serif text-base font-bold text-foreground">
            {en ? 'Practice in the terminal' : '去实战练'}
          </span>
          <p className="mt-0.5 text-sm text-muted-foreground">
            {en ? (ENGLISH_LABELS[entry.label] ?? 'Apply this lesson to a live market chart.') : entry.label}
          </p>
        </div>
        <ArrowUpRight className="h-5 w-5 shrink-0 text-midas-red transition-transform group-hover:-translate-y-0.5 group-hover:translate-x-0.5" />
      </Link>
    </section>
  )
}
