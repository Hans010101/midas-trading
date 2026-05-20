'use client'

/**
 * 左侧 60px 绘图工具栏 · 0011 ADR § 8 实装(M1 第一波)。
 *
 * 工具(M1 第一波 6 项):
 * - 趋势线 / 水平线 / 垂直线 / 矩形 / 文字 / 清空
 * - 斐波 / 通道 / 多边形 defer M1 后续
 *
 * 实装:点击 → chart.createOverlay({ name: 'straightLine' / 'rect' / ... })
 * 用户继续在 K 线上点击设置 anchor 完成绘制。
 */

import {
  Eraser,
  MoveHorizontal,
  MoveVertical,
  Square,
  TrendingUp,
  Type,
} from 'lucide-react'
import type { ReactNode } from 'react'
import { toast } from 'sonner'

import { useChartInstance } from '@/lib/chart-instance-context'
import { ensureMidasOverlays } from '@/lib/klinecharts-extensions'
import { cn } from '@/lib/utils'

interface ToolDef {
  /** klinecharts overlay name */
  overlay: string
  /** 显示名 */
  label: string
  /** lucide 图标 */
  icon: ReactNode
}

const TOOLS: ToolDef[] = [
  { overlay: 'straightLine', label: '趋势线', icon: <TrendingUp className="h-4 w-4" /> },
  { overlay: 'horizontalStraightLine', label: '水平线', icon: <MoveHorizontal className="h-4 w-4" /> },
  { overlay: 'verticalStraightLine', label: '垂直线', icon: <MoveVertical className="h-4 w-4" /> },
  // klinecharts 没有 'rect' overlay 模板,只有 rect 图元,
  //   之前用 'rect' 静默不画,本次跟随 chan-overlay 切到自定义 midas-rect
  { overlay: 'midas-rect', label: '矩形', icon: <Square className="h-4 w-4" /> },
  { overlay: 'simpleAnnotation', label: '文字标注', icon: <Type className="h-4 w-4" /> },
]

const USER_DRAW_GROUP = 'midas-user-draw'

export function ToolBar() {
  const { chart } = useChartInstance()

  function startTool(t: ToolDef) {
    if (!chart) {
      toast.error('K 线未就绪')
      return
    }
    // 确保 midas-rect / midas-fractal 已注册(幂等)
    ensureMidasOverlays()
    try {
      chart.createOverlay({
        name: t.overlay,
        groupId: USER_DRAW_GROUP,
        styles: {
          line: { color: '#C8102E', size: 1.5 },
          rect: {
            style: 'stroke_fill',
            color: 'rgba(200, 16, 46, 0.06)',
            borderColor: '#C8102E',
            borderSize: 1,
          },
          text: { color: '#1A1A1A', size: 12 },
        },
      } as never)
    } catch (e) {
      console.warn('[tool-bar] createOverlay failed:', e)
      toast.error('绘图失败 · 请重试')
    }
  }

  function clearUserDraws() {
    if (!chart) return
    try {
      chart.removeOverlay({ groupId: USER_DRAW_GROUP } as never)
      toast.success('已清空标注')
    } catch {
      /* 无 overlay 时忽略 */
    }
  }

  return (
    <aside
      className="flex w-[60px] shrink-0 flex-col items-center gap-1 border-r border-paper bg-background py-3"
      aria-label="绘图工具栏"
    >
      {TOOLS.map((t) => (
        <button
          key={t.overlay}
          type="button"
          onClick={() => startTool(t)}
          title={`${t.label} · 点击工具后,在 K 线上点击设置端点`}
          className={cn(
            'flex h-9 w-9 items-center justify-center rounded-md border border-transparent text-muted-foreground transition-colors',
            'hover:border-midas-red hover:bg-midas-red-glow hover:text-midas-red',
          )}
        >
          {t.icon}
        </button>
      ))}

      <div className="my-1 h-px w-8 bg-paper" />

      <button
        type="button"
        onClick={clearUserDraws}
        title="清空所有手动绘图(不影响缠论标注)"
        className="flex h-9 w-9 items-center justify-center rounded-md border border-transparent text-muted-foreground transition-colors hover:border-midas-red hover:bg-midas-red-glow hover:text-midas-red"
      >
        <Eraser className="h-4 w-4" />
      </button>

      <div className="mt-3 rounded-md border border-paper bg-cream px-1.5 py-2 text-center">
        <div className="text-[9px] leading-tight text-muted-foreground/60">
          斐波 / 通道
        </div>
        <span className="mt-1 inline-block rounded-full bg-gold/15 px-1 py-0.5 font-mono text-[8px] font-bold text-gold">
          M1+
        </span>
      </div>

      <div className="mt-auto text-[8px] leading-tight text-muted-foreground/50 [writing-mode:vertical-rl]">
        不构成投资建议
      </div>
    </aside>
  )
}

// 暴露 group id 供 chan-overlay 协调避免冲突
export const USER_DRAW_GROUP_ID = USER_DRAW_GROUP
