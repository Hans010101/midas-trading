'use client'

/**
 * KLineChart React wrapper(基于 klinecharts@10)。
 *
 * 数据流:
 *   useKline → query.data → dataRef → klinecharts DataLoader.getBars(callback)
 *
 * klinecharts v10 移除了 v9 的 `applyNewData`,改 DataLoader 模式:
 *   1. chart.setDataLoader({ getBars }) 注册回调
 *   2. chart.setSymbol(...) 触发 getBars
 *   3. getBars 用 callback(data) 喂数据
 *
 * 我们用一个稳定的 dataRef 作为桥(getBars 总是读最新),
 * query 数据更新时通过 setSymbol 再次触发 getBars 重渲。
 */

import { type Chart, type KLineData, type Period as KLPeriod, dispose, init } from 'klinecharts'
import { useEffect, useRef } from 'react'
import type { Market, Period } from '@midas/shared'

import { EmptyKline } from '@/components/chart/empty-kline'
import { useKline } from '@/hooks/use-kline'
import { MarketApiError } from '@/lib/api/market'
import { type ChartColors, useChartColors } from '@/lib/chart-colors'
import type { IndicatorName } from '@/lib/store/workbench-store'

// ★暗黑 P1:klinecharts 全量色板(明暗两套)· 涨跌读 CSS 变量(theme×color_pref 感知)·
//   网格/坐标轴/文字/十字线/tooltip 随主题切换 · 浅色值 = 原硬编码(零回归)。
function buildKlineStyles(c: ChartColors, isMobile: boolean): Record<string, unknown> {
  const crossText = { color: '#FFFFFF', backgroundColor: c.crosshair, borderColor: c.crosshair }
  return {
    candle: {
      bar: {
        upColor: c.up,
        downColor: c.down,
        upBorderColor: c.up,
        downBorderColor: c.down,
        upWickColor: c.up,
        downWickColor: c.down,
        noChangeColor: '#94949C',
      },
      tooltip: {
        legend: { color: c.axisText },
        ...(isMobile ? { showRule: 'follow_cross' as const } : {}),
      },
    },
    indicator: { tooltip: { legend: { color: c.axisText } } },
    grid: { horizontal: { color: c.grid }, vertical: { color: c.grid } },
    crosshair: {
      horizontal: { line: { color: c.crosshair }, text: crossText },
      vertical: { line: { color: c.crosshair }, text: crossText },
    },
    xAxis: { axisLine: { color: c.axisLine }, tickLine: { color: c.axisLine }, tickText: { color: c.axisText } },
    yAxis: { axisLine: { color: c.axisLine }, tickLine: { color: c.axisLine }, tickText: { color: c.axisText } },
  }
}

const PERIOD_TO_KL: Record<Period, KLPeriod> = {
  '1m': { type: 'minute', span: 1 },
  '5m': { type: 'minute', span: 5 },
  '15m': { type: 'minute', span: 15 },
  '30m': { type: 'minute', span: 30 },
  '1h': { type: 'hour', span: 1 },
  '1d': { type: 'day', span: 1 },
  '1w': { type: 'week', span: 1 },
}

interface KlineChartProps {
  symbol: string
  market: Market
  period: Period
  /** 'spot'(默认)现货 · 'perp' USDT-M 永续合约。不传 → spot,工作台原行为不变。 */
  instrument?: 'spot' | 'perp'
  /** 指标开关 · 父组件从 useWorkbenchStore 读取后传入 */
  indicators?: Record<IndicatorName, boolean>
  /** EmptyKline 触发"切到日 K"时的回调(父组件管 period 状态)*/
  onSwitchToDaily?: () => void
  /** chart 实例就绪回调 · 缠论 overlay / 绘图工具栏需要 chart instance */
  onChartReady?: (chart: Chart) => void
  /**
   * 可选 · 给指定指标传 klinecharts 样式覆盖(DeepPartial<IndicatorStyle>)。
   * 不传则用 klinecharts 内置默认样式(工作台原行为不变)。
   * crypto-preview 用它把 MACD 柱改成「红涨绿跌」(A 股传统 · CLAUDE.md 视觉系统)。
   */
  indicatorStyles?: Partial<Record<IndicatorName, Record<string, unknown>>>
}

export function KlineChart({
  symbol,
  market,
  period,
  instrument,
  indicators,
  onSwitchToDaily,
  onChartReady,
  indicatorStyles,
}: KlineChartProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const chartRef = useRef<Chart | null>(null)
  const dataRef = useRef<KLineData[]>([])

  const query = useKline({ symbol, market, period, instrument })
  const colors = useChartColors() // ★暗黑 P1:明暗切换 / 涨跌偏好 → setStyles 重套色板

  // 1. dataRef 始终保持最新查询数据(getBars 用闭包读取)
  useEffect(() => {
    if (query.status === 'success' && query.data.items.length > 0) {
      dataRef.current = query.data.items.map((k) => ({
        timestamp: new Date(k.ts).getTime(),
        open: k.open,
        high: k.high,
        low: k.low,
        close: k.close,
        volume: k.volume,
        turnover: k.amount ?? 0,
      }))
    } else {
      dataRef.current = []
    }
  }, [query.status, query.data])

  // 2. chart init/dispose(整个 mount 周期只一次)
  useEffect(() => {
    const el = containerRef.current
    if (!el) return

    const chart = init(el)
    if (!chart) return
    chartRef.current = chart

    // ★setStyles(涨跌色 + 网格/坐标轴/文字/十字线)移到下方 theme 反应式 effect,
    //   明暗切换 / 涨跌偏好变化时重套色板(不重建 chart)· 移动端 tooltip showRule 也在那处理。

    chart.setDataLoader({
      getBars: ({ type, callback }) => {
        callback(dataRef.current)
        // init 加载完成后默认滚到最新(任何 K 线工具的默认体验)
        if (type === 'init') {
          requestAnimationFrame(() => chartRef.current?.scrollToRealTime(0))
        }
      },
    })

    // 暴露 chart instance 给父组件(缠论 overlay / 绘图工具用)
    onChartReady?.(chart)

    return () => {
      dispose(el)
      chartRef.current = null
    }
  }, [onChartReady])

  // ★暗黑 P1:色板 theme 反应式(明暗切换 / 涨跌偏好 → 重套 setStyles · 不重建 chart)。
  //   ★浅色值 = 原硬编码(零回归)· 涨跌读 CSS 变量(暗色 #F0495E/#1FA588 · color_pref 翻转)。
  useEffect(() => {
    const chart = chartRef.current
    if (!chart) return
    const isMobile = window.matchMedia('(max-width: 1023px)').matches
    chart.setStyles(buildKlineStyles(colors, isMobile))
  }, [colors])

  // 3. props 变化(symbol/market/period) → 同步给 chart
  useEffect(() => {
    const chart = chartRef.current
    if (!chart) return
    chart.setSymbol({ ticker: symbol, pricePrecision: 2, volumePrecision: 4 })
    chart.setPeriod(PERIOD_TO_KL[period])
  }, [symbol, market, period])

  // 4. query 数据更新后,强制 chart 重新触发 getBars
  useEffect(() => {
    const chart = chartRef.current
    if (!chart) return
    if (query.status !== 'success') return
    chart.setSymbol({ ticker: symbol, pricePrecision: 2, volumePrecision: 4 })
  }, [query.status, query.data, symbol])

  // 5. indicators 状态同步到 chart 实例
  useEffect(() => {
    const chart = chartRef.current
    if (!chart) return
    if (!indicators) return
    // 先清空所有指标(暴力但简单 · M0 demo 4 个指标切换不频繁,无性能压力)
    chart.removeIndicator()
    // 有 styles 覆盖时用 IndicatorCreate 对象,否则用 name 字符串(走内置默认样式)。
    // overlayOnCandle=true → 叠到主图 candle_pane(MA/BOLL,跟 K 线重叠,TradingView 式)。
    //   必须显式传 paneOptions.id='candle_pane'(+ isStack=true 不顶替 K 线),
    //   否则 klinecharts 默认会新建一个独立副图 pane → 布林带被画进独立小窗(= 之前的 bug)。
    // overlayOnCandle=false → 独立副图 pane(MACD/RSI),保持原行为。
    // 移动刀C(B2):窄屏副图(MACD/RSI)高度压到 ~90px(容器 400px 的 ~22%,主图为主);
    // 桌面不传 height = klinecharts 默认占比,零变化。
    const isMobile = window.matchMedia('(max-width: 1023px)').matches
    const make = (name: IndicatorName, overlayOnCandle: boolean) => {
      const styles = indicatorStyles?.[name]
      const value = (styles ? { name, styles } : name) as never
      if (overlayOnCandle) {
        chart.createIndicator(value, true, { id: 'candle_pane' })
      } else {
        chart.createIndicator(value, false, isMobile ? { height: 90 } : undefined)
      }
    }
    if (indicators.MA) make('MA', true)
    if (indicators.BOLL) make('BOLL', true)
    if (indicators.MACD) make('MACD', false)
    if (indicators.RSI) make('RSI', false)
  }, [indicators, indicatorStyles])

  // ========== Empty / Error states ==========
  if (query.status === 'error') {
    const err = query.error
    if (err instanceof MarketApiError) {
      if (err.kind === 'not-found') {
        return <div data-kline-state="not-found"><EmptyKline reason="not-found" /></div>
      }
      if (err.kind === 'unavailable' || err.kind === 'bad-gateway') {
        return <div data-kline-state="unavailable"><EmptyKline reason="unavailable" onRetry={() => void query.refetch()} /></div>
      }
    }
    return <div data-kline-state="unavailable"><EmptyKline reason="unavailable" onRetry={() => void query.refetch()} /></div>
  }

  if (query.status === 'success' && query.data.items.length === 0) {
    return <div data-kline-state="empty"><EmptyKline reason="empty" onSwitchToDaily={onSwitchToDaily} /></div>
  }

  return (
    <div
      ref={containerRef}
      data-kline-state={query.status === 'success' ? 'ready' : 'loading'}
      className="h-full w-full min-h-[400px] bg-cream"
    />
  )
}
