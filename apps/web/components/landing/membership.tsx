/**
 * 官网区块 · 会员体系(原 Pricing 改造)· 官网刀1,"进阶解锁"接口区。
 *
 * 零重构保证:独立组件 + #membership 锚点;会员第二波只填右卡内容,不动布局。
 * 文案克制:teaser 4 条,不写价格不承诺时间。
 */

import { ArrowRight, Check, Sparkles } from 'lucide-react'
import Link from 'next/link'

const FREE_FEATURES = [
  '加密、美股、A 股、港股四市场行情与 K 线',
  'AI 沙盘助手与 AI 决策卡',
  '策略研究室回测',
  '虚拟交易与条件单',
  '飞书 / Telegram 消息推送',
]

const PRO_TEASERS = [
  '更高的 AI 分析额度',
  '更深的回测历史区间',
  '更细颗粒的数据维度',
  '专属推送通道',
]

export function Membership() {
  return (
    <section id="membership" className="border-y border-paper/60 bg-surface-card py-16">
      <div className="mx-auto max-w-4xl px-6">
        <div className="text-center">
          <h2 className="font-serif text-3xl font-bold lg:text-4xl">会员体系</h2>
          <p className="mt-3 text-sm text-muted-foreground">内测期间全功能免费开放</p>
        </div>

        <div className="mt-8 grid gap-5 md:grid-cols-2">
          {/* 左 · 内测免费版(现有全功能) */}
          <div className="rounded-2xl border border-paper bg-background p-7 shadow-md">
            <div className="inline-block rounded-full border border-midas-red/40 bg-midas-red-glow/40 px-4 py-1.5 font-mono text-xs text-midas-red">
              内测免费版 · 当前
            </div>
            <h3 className="mt-4 font-serif text-xl font-bold">全功能开放</h3>
            <ul className="mt-4 space-y-2.5 text-sm text-muted-foreground">
              {FREE_FEATURES.map((f) => (
                <li key={f} className="flex items-start gap-2">
                  <Check className="mt-0.5 h-4 w-4 shrink-0 text-midas-red" />
                  {f}
                </li>
              ))}
            </ul>
            <Link
              href="/global"
              className="mt-6 inline-flex items-center gap-2 rounded-md bg-midas-red px-5 py-2.5 text-sm font-medium text-white shadow-sm transition-colors hover:bg-midas-red-deep"
            >
              立即体验
              <ArrowRight className="h-4 w-4" />
            </Link>
          </div>

          {/* 右 · 进阶版(第二波接入 · 只填内容不动布局) */}
          <div className="rounded-2xl border-2 border-gold/40 bg-background p-7 shadow-md">
            <div className="inline-block rounded-full border border-gold bg-gold/10 px-4 py-1.5 font-mono text-xs text-gold">
              进阶版 · 即将推出
            </div>
            <h3 className="mt-4 font-serif text-xl font-bold">进阶解锁</h3>
            <ul className="mt-4 space-y-2.5 text-sm text-muted-foreground">
              {PRO_TEASERS.map((f) => (
                <li key={f} className="flex items-start gap-2">
                  <Sparkles className="mt-0.5 h-4 w-4 shrink-0 text-gold" />
                  {f}
                </li>
              ))}
            </ul>
            <p className="mt-6 text-xs text-muted-foreground/60">
              方案打磨中 · 内测用户将优先获得通知
            </p>
          </div>
        </div>
      </div>
    </section>
  )
}
