'use client'

/**
 * 左侧 60px 绘图工具栏占位 · M1 实装(缠论笔/段/枢纽/中枢标注用)。
 * M0 阶段只画占位 div + 说明字。
 */

export function ToolBar() {
  return (
    <aside className="flex w-[60px] shrink-0 flex-col items-center gap-2 border-r border-paper bg-cream py-3">
      <div className="text-[10px] text-muted-foreground/70 [writing-mode:vertical-rl]">
        绘图工具栏 · M1
      </div>
    </aside>
  )
}
