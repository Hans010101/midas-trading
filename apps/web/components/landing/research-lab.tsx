/**
 * 官网区块 · 验证想法(策略研究室)· 官网刀1 新增,旅程第三步。
 *
 * 叙事:回测让想法先过历史数据这一关 + AI 判断命中率回看(敢被检验)。
 * SSG 静态,截图占位刀2 替换。
 */

import { FlaskConical } from 'lucide-react'
import Image from 'next/image'

export function ResearchLab() {
  return (
    <section id="lab" className="mx-auto max-w-6xl px-6 py-20">
      <div className="grid items-center gap-10 lg:grid-cols-2">
        {/* 左 · 回测报告实拍(指标卡+权益曲线+回撤 · 竖构图按原始 900×1106 比例)
            · lg 在左与沙盘区交错 */}
        <div className="relative aspect-[900/1106] overflow-hidden rounded-xl border border-paper bg-background shadow-lg">
          <Image
            src="/marketing/backtest.png"
            alt="策略回测报告:权益曲线与关键指标"
            fill
            className="object-contain"
            sizes="(max-width: 1024px) 100vw, 50vw"
          />
        </div>

        {/* 右 · 叙事(DOM 在后 → lg 双列时天然在右,与沙盘区左右交错) */}
        <div>
          <p className="mb-2 flex items-center gap-2 text-xs uppercase tracking-[0.3em] text-gold">
            <FlaskConical className="h-4 w-4" />
            策略研究室
          </p>
          <h2 className="font-serif text-3xl font-bold leading-snug lg:text-4xl">
            想法,先过数据这一关
          </h2>
          <p className="mt-4 text-sm leading-relaxed text-muted-foreground lg:text-base">
            「感觉能行」不算数。选好策略、标的与时间段,研究室用历史行情把这条想法完整跑一遍——收益曲线、胜率、最大回撤,清清楚楚摆在报告里。
          </p>
          <ul className="mt-5 space-y-2 text-sm text-muted-foreground">
            <li className="flex gap-2">
              <span className="text-midas-red">·</span>
              一键回测:策略 × 标的 × 区间,几分钟出完整报告
            </li>
            <li className="flex gap-2">
              <span className="text-midas-red">·</span>
              收益曲线 + 每笔交易明细,赚在哪亏在哪都能复盘
            </li>
            <li className="flex gap-2">
              <span className="text-midas-red">·</span>
              AI 判断命中率回看:它说对了多少,系统自己记账,敢被检验
            </li>
          </ul>
          <p className="mt-4 text-xs text-muted-foreground/60">
            历史表现不代表未来收益,回测结果仅供参考,不构成投资建议。
          </p>
        </div>
      </div>
    </section>
  )
}
