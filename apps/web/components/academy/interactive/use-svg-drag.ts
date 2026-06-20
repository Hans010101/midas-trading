'use client'

import { useCallback, useRef, useState, type PointerEvent as ReactPointerEvent } from 'react'

/** 线性映射:定义域 [d0,d1] 上的 v → 值域 [r0,r1]。反向传参即「像素→值」。 */
export function linearScale(v: number, d0: number, d1: number, r0: number, r1: number): number {
  if (d1 === d0) return r0
  return r0 + ((v - d0) / (d1 - d0)) * (r1 - r0)
}

/** 把数值夹在 [min,max] 内 */
export function clampValue(v: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, v))
}

interface UseVerticalDragArgs {
  /** 结构化类型,兼容 React 18/19 的 ref */
  svgRef: { current: SVGSVGElement | null }
  /** SVG viewBox 的高度(逻辑坐标系) */
  viewBoxHeight: number
  /** 拖动回调:把当前 SVG 逻辑 Y 交给组件,由组件换算成数值并写回 state */
  onMove: (id: string, svgY: number) => void
}

/**
 * 垂直拖拽 hook(Pointer Events 统一鼠标 + 触摸)。
 * 用法:onPointerDown(id) 绑各手柄;onPointerMove/Up/Cancel 绑 <svg> 根。
 * pointerdown 时把指针捕获到 svg 根 → 后续 move 不论指针移到哪都落在 svg 上,多手柄安全。
 */
export function useVerticalDrag({ svgRef, viewBoxHeight, onMove }: UseVerticalDragArgs) {
  const [activeId, setActiveId] = useState<string | null>(null)
  const activeRef = useRef<string | null>(null)

  const toSvgY = useCallback(
    (clientY: number): number => {
      const svg = svgRef.current
      if (!svg) return 0
      const rect = svg.getBoundingClientRect()
      if (rect.height === 0) return 0
      return ((clientY - rect.top) / rect.height) * viewBoxHeight
    },
    [svgRef, viewBoxHeight],
  )

  const onPointerDown = useCallback(
    (id: string) =>
      (e: ReactPointerEvent): void => {
        e.preventDefault()
        const svg = svgRef.current
        if (svg) {
          try {
            svg.setPointerCapture(e.pointerId)
          } catch {
            /* 个别环境不支持,忽略 */
          }
        }
        activeRef.current = id
        setActiveId(id)
        onMove(id, toSvgY(e.clientY))
      },
    [onMove, svgRef, toSvgY],
  )

  const onPointerMove = useCallback(
    (e: ReactPointerEvent): void => {
      if (activeRef.current == null) return
      e.preventDefault()
      onMove(activeRef.current, toSvgY(e.clientY))
    },
    [onMove, toSvgY],
  )

  const endDrag = useCallback((): void => {
    activeRef.current = null
    setActiveId(null)
  }, [])

  return { activeId, onPointerDown, onPointerMove, onPointerUp: endDrag, onPointerCancel: endDrag }
}
