'use client'

/**
 * 左侧 60px 绘图工具栏占位 · M1 实装(缠论笔/段/枢纽/中枢标注用)。
 * M0 阶段画米白卡 + 帝王金 M1 徽章,告知用户「这里是工具栏,尚未启用」。
 */

export function ToolBar() {
  return (
    <aside className="flex w-[60px] shrink-0 flex-col items-center gap-3 border-r border-paper bg-background py-4">
      <div className="flex flex-col items-center gap-2 rounded-md border border-paper bg-cream px-1.5 py-3 shadow-sm">
        <div className="text-xl leading-none" aria-hidden="true">
          🎨
        </div>
        <div className="text-[10px] leading-tight text-foreground [writing-mode:vertical-rl]">
          专业绘图
        </div>
        <span className="rounded-full bg-gold/15 px-1.5 py-0.5 font-mono text-[9px] font-bold text-gold">
          M1
        </span>
      </div>
      <div className="text-[9px] leading-tight text-muted-foreground/60 [writing-mode:vertical-rl]">
        缠论 笔/段/枢纽
      </div>
    </aside>
  )
}
