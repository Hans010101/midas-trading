'use client'

/**
 * 缠论标注层 · 0011 ADR § 6 · 2026-05-20 配色调整 v2。
 *
 * 配色规则(产品负责人 2026-05-20 拍板):
 * - 笔 · segment · 帝王金 #B8860B(不分上升/下降)
 *   理由:深红跟 K 线朱红涨色冲突 · 改金色醒目又不跟涨跌色冲突
 * - 中枢 · rect · 淡灰蓝中性 rgba(100,130,160,0.18) + 实线边 #6482A0
 *   理由:震荡区间用中性色 · 跟笔的金色明确区分 · 视觉系统外唯一新增色
 * - 顶分型(G) · ▽ 墨绿 #0F6E5F · 画在 K 线上方 offset y=-14
 *   语义:顶分型预示可能转跌 → 用墨绿(产品里墨绿=跌)
 * - 底分型(D) · △ 朱红 #DC143C · 画在 K 线下方 offset y=+14
 *   语义:底分型预示可能转涨 → 用朱红(产品里朱红=涨)
 *   分型颜色跟产品涨跌语义一致,用户零学习成本。
 *
 * 图层顺序(底 → 顶):
 *   1. 中枢矩形(背景层)
 *   2. 笔连线(在矩形上方,清晰可见)
 *   3. 分型三角(标记最上层)
 *
 * **自定义 overlay `midas-fractal`**:klinecharts 自带的 `simpleAnnotation`
 *   强制带一条 50px 垂直虚线 + 多边形箭头(蓝色方块外观)·
 *   不符合「干净彩色三角标记」需求,本组件 module 加载时注册自定义 overlay,
 *   只画文字符号,不画线和箭头。
 *
 * 单 useEffect 处理所有状态 · 避免 clear / create 竞态。
 */

import type { Chart } from 'klinecharts'
import { useEffect } from 'react'

import { useChan } from '@/hooks/use-chan'
import { ensureMidasOverlays } from '@/lib/klinecharts-extensions'
import { useWorkbenchStore } from '@/lib/store/workbench-store'

interface Props {
  chart: Chart | null
  /**
   * 可选 override · 不传则从 useWorkbenchStore 读(工作台原行为不变)。
   * crypto-preview 详情页用 props 驱动 · 不污染全局 workbench 状态。
   */
  symbol?: string
  market?: import('@midas/shared').Market
  period?: import('@midas/shared').Period
  enabled?: boolean
}

const CHAN_GROUP_ID = 'midas-chan-overlay'

// 配色 token(本组件常量 · 跟 CLAUDE.md 视觉系统对齐)
const COLOR_BI = '#B8860B'                          // 帝王金 · 笔连线
const COLOR_ZS_FILL = 'rgba(100, 130, 160, 0.18)'   // 淡灰蓝填充
const COLOR_ZS_BORDER = '#6482A0'                   // 淡灰蓝实线边
const COLOR_FX_TOP = '#0F6E5F'                      // 墨绿 · 顶分型(预示转跌)
const COLOR_FX_BOTTOM = '#DC143C'                   // 朱红 · 底分型(预示转涨)
// 0012 二波 · 买卖点 · 买点用「涨色」朱红 / 卖点用「跌色」墨绿
const COLOR_BSP_BUY = '#DC143C'                     // B1/B2/B3
const COLOR_BSP_SELL = '#0F6E5F'                    // S1/S2/S3

// 自定义 overlay 注册位于 lib/klinecharts-extensions.ts(midas-rect + midas-fractal)·
// 任何需要的组件 import 即触发注册副作用,幂等。

export function ChanOverlay({
  chart,
  symbol: symbolProp,
  market: marketProp,
  period: periodProp,
  enabled: enabledProp,
}: Props) {
  const storeSymbol = useWorkbenchStore((s) => s.symbol)
  const storeMarket = useWorkbenchStore((s) => s.market)
  const storePeriod = useWorkbenchStore((s) => s.period)
  const storeChanEnabled = useWorkbenchStore((s) => s.chanEnabled)

  // props override 优先 · 不传则用 store(工作台原行为)
  const symbol = symbolProp ?? storeSymbol
  const market = marketProp ?? storeMarket
  const period = periodProp ?? storePeriod
  const chanEnabled = enabledProp ?? storeChanEnabled

  const { data } = useChan({
    symbol, market, period,
    enabled: chanEnabled,
  })

  useEffect(() => {
    if (!chart) return

    // 确保自定义 overlay 已注册(幂等 · 详见 lib/klinecharts-extensions.ts)
    ensureMidasOverlays()

    // 1. 先清旧 chan overlay(幂等)
    try {
      chart.removeOverlay({ groupId: CHAN_GROUP_ID } as never)
    } catch {
      /* ignore · 无 overlay */
    }

    if (!chanEnabled || !data) return

    // 2. 构造 overlay 数组 · 顺序就是绘制顺序(先画的在底)
    const overlays: unknown[] = []

    // 第 1 层 · 中枢矩形(背景)· 必须在笔之前 push,才能被笔连线覆盖在下层
    // 用自定义 midas-rect overlay · klinecharts 没有 'rect' overlay 模板,
    // 之前用 name: 'rect' 静默失败什么也不画
    for (const zs of data.zhongshus) {
      overlays.push({
        name: 'midas-rect',
        groupId: CHAN_GROUP_ID,
        paneId: 'candle_pane',
        lock: true,
        points: [
          { timestamp: new Date(zs.start_ts).getTime(), value: zs.high },
          { timestamp: new Date(zs.end_ts).getTime(), value: zs.low },
        ],
        styles: {
          rect: {
            // drawRect 默认 style='fill' · 改 'stroke_fill' 才能同时画填充 + 边
            style: 'stroke_fill',
            color: COLOR_ZS_FILL,
            borderColor: COLOR_ZS_BORDER,
            borderSize: 1,
            borderStyle: 'solid',
          },
        },
      })
    }

    // 第 2 层 · 笔连线(在中枢上方)
    for (const bi of data.bis) {
      overlays.push({
        name: 'segment',
        groupId: CHAN_GROUP_ID,
        paneId: 'candle_pane',
        lock: true,
        points: [
          { timestamp: new Date(bi.start_ts).getTime(), value: bi.start_price },
          { timestamp: new Date(bi.end_ts).getTime(), value: bi.end_price },
        ],
        styles: { line: { color: COLOR_BI, size: 1.5 } },
      })
    }

    // 第 3 层 · 分型三角(最上层 · 自定义 midas-fractal overlay · 无虚线/无箭头/无背景)
    for (const fx of data.fractals) {
      const isTop = fx.kind === 'G'
      // 注意:offset 通过预先算偏移到 point 的 value 实现不准(price scale 非线性)
      // klinecharts 的 text 风格的 offset 用于 figure 内部偏移,这里通过 styles 设置
      overlays.push({
        name: 'midas-fractal',
        groupId: CHAN_GROUP_ID,
        paneId: 'candle_pane',
        lock: true,
        points: [
          { timestamp: new Date(fx.ts).getTime(), value: fx.price },
        ],
        // 顶分型 ▽(空心下三角 · 预示转跌)/ 底分型 △(空心上三角 · 预示转涨)
        extendData: isTop ? '▽' : '△',
        styles: {
          text: {
            color: isTop ? COLOR_FX_TOP : COLOR_FX_BOTTOM,
            size: 14,
            family: 'Helvetica Neue, Arial, sans-serif',
            weight: 'bold',
            // klinecharts overlay text 默认 backgroundColor=BLUE + 4px padding
            //   → 文字外面会画一个蓝色实心方块 · 必须清零才能得到「干净文字」
            backgroundColor: 'transparent',
            borderColor: 'transparent',
            borderSize: 0,
            paddingLeft: 0,
            paddingRight: 0,
            paddingTop: 0,
            paddingBottom: 0,
            // y 偏移在 createPointFigures 里基于 extendData(▽/△)做了 ±14px
          },
        },
      })
    }

    // 第 4 层 · 缠论买卖点(B1-3 / S1-3)· 0012 二波 · 复用 midas-fractal 自定义 overlay
    // 显示在分型上方,可一目了然识别趋势节点
    for (const bsp of data.buy_sell_points) {
      const isBuy = bsp.kind.startsWith('B')
      overlays.push({
        name: 'midas-fractal',
        groupId: CHAN_GROUP_ID,
        paneId: 'candle_pane',
        lock: true,
        points: [
          { timestamp: new Date(bsp.ts).getTime(), value: bsp.price },
        ],
        // 显示 B1/B2/B3/S1/S2/S3 字符 · midas-fractal 按首字母决定上下偏移
        // (S → K 线上方较高 · B → K 线下方较低 · 避开分型)
        extendData: bsp.kind,
        styles: {
          text: {
            color: isBuy ? COLOR_BSP_BUY : COLOR_BSP_SELL,
            size: 11,                  // 字符标签 · 比分型小一点 · 不喧宾夺主
            family: 'JetBrains Mono, Consolas, monospace',
            weight: 'bold',
            backgroundColor: 'transparent',
            borderColor: 'transparent',
            borderSize: 0,
            paddingLeft: 0,
            paddingRight: 0,
            paddingTop: 0,
            paddingBottom: 0,
          },
        },
      })
    }

    try {
      chart.createOverlay(overlays as never)
    } catch (e) {
      console.warn('[chan-overlay] createOverlay failed:', e)
    }
  }, [chart, chanEnabled, data])

  return null
}
