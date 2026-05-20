/**
 * klinecharts 自定义 overlay 注册 · 0011 ADR § 配色调整 v2 配套。
 *
 * klinecharts 没有 'rect' / 'rectangle' overlay 模板(只有 rect 图元),
 * 也没有「干净文字标记」模板(simpleAnnotation 强制带 50px 虚线 + 多边形箭头)。
 * 本模块在 module 加载时注册两个自定义 overlay:
 *
 *   - midas-rect    · 两点矩形 · 用 rect 图元 · 支持 fill + stroke
 *                     · 用于:缠论中枢 + 用户手动绘图工具栏「矩形」
 *   - midas-fractal · 干净文字标记 · 用 text 图元 · 无虚线/无箭头/无背景框
 *                     · 用于:缠论顶/底分型 ▽ △
 *
 * 任何需要这两个 overlay 的组件都先 import 这个模块,确保注册副作用执行。
 * registerOverlay 内部 Map<name, OverlayCtor>,同名后注册的覆盖前面的,幂等。
 */

import { registerOverlay } from 'klinecharts'

let registered = false

export function ensureMidasOverlays() {
  if (registered) return
  registered = true

  registerOverlay({
    name: 'midas-rect',
    totalStep: 3,
    needDefaultPointFigure: false,
    needDefaultXAxisFigure: false,
    needDefaultYAxisFigure: false,
    createPointFigures: ({
      coordinates,
    }: {
      coordinates: { x: number; y: number }[]
    }) => {
      if (coordinates.length < 2) return []
      const [p1, p2] = coordinates
      const x = Math.min(p1.x, p2.x)
      const y = Math.min(p1.y, p2.y)
      const width = Math.abs(p2.x - p1.x)
      const height = Math.abs(p2.y - p1.y)
      return [
        {
          type: 'rect',
          attrs: { x, y, width, height },
          ignoreEvent: true,
        },
      ]
    },
  } as never)

  registerOverlay({
    name: 'midas-fractal',
    totalStep: 2,
    needDefaultPointFigure: false,
    needDefaultXAxisFigure: false,
    needDefaultYAxisFigure: false,
    createPointFigures: ({
      overlay,
      coordinates,
    }: {
      overlay: { extendData?: string }
      coordinates: { x: number; y: number }[]
    }) => {
      const text = overlay.extendData ?? ''
      // 偏移方向规则:
      //   - 文字 ▽(顶分型)  → K 线上方 -14
      //   - 文字以 'S' 开头(卖点 S1/S2/S3)→ K 线上方 -18(避开分型)
      //   - 文字 △(底分型)/ B 开头(买点 B1/B2/B3) → K 线下方
      const isTopFractal = text === '▽'
      const isSellPoint = text.startsWith('S')
      const isAbove = isTopFractal || isSellPoint
      const yOffset = isAbove ? (isSellPoint ? -22 : -14) : (text.startsWith('B') ? 22 : 14)
      return [
        {
          type: 'text',
          attrs: {
            x: coordinates[0].x,
            y: coordinates[0].y + yOffset,
            text,
            align: 'center',
            baseline: 'middle',
          },
          ignoreEvent: true,
        },
      ]
    },
  } as never)
}
