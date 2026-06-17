/**
 * 官网区块 · 会员体系 · 免费版 vs Pro 权益对比(★不展示价格 · 价格在会员页揭晓)。
 *
 * 与产品现状对齐(已收费):免费版可看行情/K线/缠论 + 低额度 AI;
 * Pro 解锁高额度 + AI 决策卡 / 实战策略清单(专属)。
 * 复用会员页(membership-section.tsx)卡片/权益语言;保留 #membership 锚点(TopNav/Footer 链接)。
 */

import { ArrowRight, Check, Sparkles } from 'lucide-react'
import Link from 'next/link'

// 免费版能做什么(★数字与 PLAN_QUOTAS / 会员页一致:诊断 5 / 回测 3)
const FREE_FEATURES = [
  'AI 沙盘诊断 5 次 / 月',
  '策略回测 3 次 / 月',
  '加密 · 美股 · A 股 · 港股 四市场 K 线与行情',
  '合约维度图 · 缠论自动标注',
  '虚拟交易与条件单 · 飞书 / Telegram 推送',
]

// Pro 解锁什么(exclusive 标★ · 数字与会员页一致:诊断 300 / 回测 150)
const PRO_FEATURES: { text: string; exclusive?: boolean }[] = [
  { text: 'AI 沙盘诊断 300 次 / 月' },
  { text: '策略回测 150 次 / 月' },
  { text: 'AI 决策卡 · 综合评分 + 多空研判 + 关键位', exclusive: true },
  { text: '实战策略清单 · 命中即提示的可执行策略', exclusive: true },
]

export function Membership() {
  return (
    <section id="membership" className="border-y border-paper/60 bg-surface-card py-16">
      <div className="mx-auto max-w-4xl px-6">
        <div className="text-center">
          <h2 className="font-serif text-3xl font-bold lg:text-4xl">会员体系</h2>
          <p className="mt-3 text-sm text-muted-foreground">
            免费起步,四市场行情与缠论标注随时看;Pro 解锁高额度 AI 与决策卡
          </p>
        </div>

        <div className="mt-8 grid items-start gap-5 md:grid-cols-2">
          {/* 左 · 免费版 */}
          <div className="flex flex-col rounded-2xl border border-paper bg-background p-7 shadow-md">
            <div className="inline-block self-start rounded-full border border-paper bg-surface-subtle px-4 py-1.5 font-mono text-xs text-muted-foreground">
              免费版
            </div>
            <h3 className="mt-4 font-serif text-xl font-bold">零成本起步</h3>
            <ul className="mt-4 flex-1 space-y-2.5 text-sm text-muted-foreground">
              {FREE_FEATURES.map((f) => (
                <li key={f} className="flex items-start gap-2">
                  <Check className="mt-0.5 h-4 w-4 shrink-0 text-midas-red" />
                  {f}
                </li>
              ))}
            </ul>
            <Link
              href="/global"
              className="mt-6 inline-flex items-center gap-2 self-start rounded-md border border-midas-red px-5 py-2.5 text-sm font-medium text-midas-red transition-colors hover:bg-midas-red-glow/40"
            >
              免费开始
              <ArrowRight className="h-4 w-4" />
            </Link>
          </div>

          {/* 右 · Pro(高亮) */}
          <div className="flex flex-col rounded-2xl border-2 border-gold/50 bg-background p-7 shadow-md">
            <div className="inline-flex items-center gap-1.5 self-start rounded-full border border-gold bg-gold/10 px-4 py-1.5 font-mono text-xs text-gold">
              <Sparkles className="h-3.5 w-3.5" />
              Pro 会员
            </div>
            <h3 className="mt-4 font-serif text-xl font-bold">解锁全部 AI 决策能力</h3>
            <ul className="mt-4 flex-1 space-y-2.5 text-sm text-foreground/90">
              {PRO_FEATURES.map((f) => (
                <li key={f.text} className="flex items-start gap-2">
                  {f.exclusive ? (
                    <Sparkles className="mt-0.5 h-4 w-4 shrink-0 text-gold" />
                  ) : (
                    <Check className="mt-0.5 h-4 w-4 shrink-0 text-gold" />
                  )}
                  <span>
                    {f.text}
                    {f.exclusive && (
                      <span className="ml-1.5 rounded bg-gold/10 px-1.5 py-0.5 text-[10px] font-medium text-gold">
                        专属
                      </span>
                    )}
                  </span>
                </li>
              ))}
            </ul>
            <p className="mt-4 flex items-center gap-1.5 text-[11px] text-gold/80">
              <Sparkles className="h-3 w-3 shrink-0" />
              更多专属功能陆续上线
            </p>
            <Link
              href="/account/membership"
              className="mt-3 inline-flex items-center gap-2 self-start rounded-md bg-midas-red px-5 py-2.5 text-sm font-medium text-white shadow-sm transition-colors hover:bg-midas-red-deep"
            >
              了解会员
              <ArrowRight className="h-4 w-4" />
            </Link>
          </div>
        </div>

        <p className="mt-6 text-center text-xs text-muted-foreground/60">
          到期自动回落免费版 · 无自动续费 · 仅供模拟交易,不构成投资建议
        </p>
      </div>
    </section>
  )
}
