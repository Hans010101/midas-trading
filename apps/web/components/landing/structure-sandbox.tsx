/**
 * 官网区块 · 看懂结构(AI 沙盘助手)· 官网刀1 新增,旅程第二步。
 *
 * 口径:四市场平等叙事 —— 覆盖范围(当前加密)用小字诚实注明,不进标题;
 * 零专业术语(11 项因子说人话)。SSG 静态,截图占位刀2 替换。
 */

import { Network } from 'lucide-react'

import { ScreenshotPlaceholder } from '@/components/landing/screenshot-placeholder'

export function StructureSandbox() {
  return (
    <section id="sandbox" className="border-y border-paper/60 bg-surface-card py-20">
      <div className="mx-auto max-w-6xl px-6">
        <div className="grid items-center gap-10 lg:grid-cols-2">
          {/* 左 · 叙事 */}
          <div>
            <p className="mb-2 flex items-center gap-2 text-xs uppercase tracking-[0.3em] text-gold">
              <Network className="h-4 w-4" />
              AI 沙盘助手
            </p>
            <h2 className="font-serif text-3xl font-bold leading-snug lg:text-4xl">
              先看懂结构,再出手
            </h2>
            <p className="mt-4 text-sm leading-relaxed text-muted-foreground lg:text-base">
              市场不止有价格。沙盘助手把多空人数、大户持仓、资金情绪等 11
              项市场结构因子放进一张关联图谱——哪些因子互相印证、哪些正在背离,一眼看清;AI
              再用中文把当前结构讲明白:现在是谁在买、谁在撤、拥挤在哪边。
            </p>
            <ul className="mt-5 space-y-2 text-sm text-muted-foreground">
              <li className="flex gap-2">
                <span className="text-midas-red">·</span>
                11 项结构因子,数值与判定分开呈现,不混为一谈
              </li>
              <li className="flex gap-2">
                <span className="text-midas-red">·</span>
                因子关联图谱:背离与共振自动识别、规则可解释
              </li>
              <li className="flex gap-2">
                <span className="text-midas-red">·</span>
                结论先行的中文结构诊断,附数据口径说明
              </li>
            </ul>
            <p className="mt-4 text-xs text-muted-foreground/60">
              当前覆盖加密市场,更多市场逐步接入。结构描述非价格预测,不构成投资建议。
            </p>
          </div>

          {/* 右 · 截图占位(刀2 换真图:/lab/assistant 结构沙盘区 · 图谱+大数字面板) */}
          <ScreenshotPlaceholder
            aspect="aspect-[16/11]"
            label="AI 沙盘助手 · 因子关联图谱与结构诊断"
          />
        </div>
      </div>
    </section>
  )
}
