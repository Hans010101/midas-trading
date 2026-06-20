/**
 * 官网区块 · 虚拟实战(原 AiChan 右半改造)· 官网刀1,旅程第四步。
 *
 * 链路叙事:AI 决策卡 → 一键虚拟下单 → 条件单守仓,全程虚拟资金。
 * ai-card 两张截图留用;条件单截图占位刀2 替换;强制 disclaimer 随区。
 */

import { Bot } from 'lucide-react'
import Image from 'next/image'

export function VirtualPractice() {
  return (
    <section id="practice" className="border-y border-paper/60 bg-surface-card py-20">
      <div className="mx-auto max-w-6xl px-6">
        <div className="text-center">
          <p className="mb-2 flex items-center justify-center gap-2 text-xs uppercase tracking-[0.3em] text-gold">
            <Bot className="h-4 w-4" />
            虚拟实战
          </p>
          <h2 className="font-serif text-3xl font-bold lg:text-4xl">
            从 AI 研判到下单守仓,全程虚拟
          </h2>
          <p className="mx-auto mt-3 max-w-2xl text-sm text-muted-foreground">
            AI 决策卡给出结构化研判与关键位;看好就一键模拟下单;再挂上止盈止损,触发自动执行——一条完整的交易闭环,不花一分真钱。
          </p>
        </div>

        <div className="mt-10 grid gap-6 md:grid-cols-3">
          {/* ① AI 决策卡(留用现截图) */}
          <figure className="flex flex-col">
            <div className="relative aspect-[5/6] overflow-hidden rounded-xl border border-paper bg-background shadow-lg">
              <Image
                src="/marketing/ai-card-top.png"
                alt="AI 决策卡:综合评分 + 结构研判"
                fill
                className="object-contain"
                sizes="(max-width: 768px) 100vw, 33vw"
              />
            </div>
            <figcaption className="mt-2 text-center text-xs text-muted-foreground/70">
              ① AI 决策卡 · 评分与关键位
            </figcaption>
          </figure>

          {/* ② 一键虚拟下单(留用现截图) */}
          <figure className="flex flex-col">
            <div className="relative aspect-[5/6] overflow-hidden rounded-xl border border-paper bg-background shadow-lg">
              <Image
                src="/marketing/ai-card-bottom.png"
                alt="一键模拟下单面板(全程虚拟)"
                fill
                className="object-contain"
                sizes="(max-width: 768px) 100vw, 33vw"
              />
            </div>
            <figcaption className="mt-2 text-center text-xs text-muted-foreground/70">
              ② 一键模拟下单 · 虚拟资金
            </figcaption>
          </figure>

          {/* ③ 条件单(止盈止损弹层实拍 400×401 方图 · 同框 5/6 + contain 与两卡对齐) */}
          <figure className="flex flex-col">
            <div className="relative aspect-[5/6] overflow-hidden rounded-xl border border-paper bg-background shadow-lg">
              <Image
                src="/marketing/conditional.png"
                alt="止盈止损条件单设置"
                fill
                className="object-contain"
                sizes="(max-width: 768px) 100vw, 33vw"
              />
            </div>
            <figcaption className="mt-2 text-center text-xs text-muted-foreground/70">
              ③ 条件单守仓 · 触发自动执行
            </figcaption>
          </figure>
        </div>
      </div>
    </section>
  )
}
