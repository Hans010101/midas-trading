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
import type { IndicatorName } from '@/lib/store/workbench-store'

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
  indicators,
  onSwitchToDaily,
  onChartReady,
  indicatorStyles,
}: KlineChartProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const chartRef = useRef<Chart | null>(null)
  const dataRef = useRef<KLineData[]>([])

  const query = useKline({ symbol, market, period })

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

    // 视觉 token · 04 文档 + CLAUDE.md 视觉系统
    chart.setStyles({
      candle: {
        bar: {
          upColor: '#DC143C', // bull 朱红
          downColor: '#0F6E5F', // bear 墨绿
          upBorderColor: '#DC143C',
          downBorderColor: '#0F6E5F',
          upWickColor: '#DC143C',
          downWickColor: '#0F6E5F',
          noChangeColor: '#94949C', // ink-faint
        },
      },
      crosshair: {
        horizontal: { line: { color: '#C8102E' } }, // 中国红
        vertical: { line: { color: '#C8102E' } },
      },
      grid: {
        horizontal: { color: '#F0EEE8' },
        vertical: { color: '#F0EEE8' },
      },
    })

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
    // 有 styles 覆盖时用 IndicatorCreate 对象,否则用 name 字符串(走内置默认样式)
    const make = (name: IndicatorName, isStack: boolean) => {
      const styles = indicatorStyles?.[name]
      if (styles) {
        chart.createIndicator({ name, styles } as never, isStack)
      } else {
        chart.createIndicator(name, isStack)
      }
    }
    // 按状态重建:MA / BOLL 主图叠加(isStack=true);MACD / RSI 副图独立 pane
    if (indicators.MA) make('MA', true)
    if (indicators.BOLL) make('BOLL', true)
    if (indicators.MACD) make('MACD', false)
    if (indicators.RSI) make('RSI', false)
  }, [indicators, indicatorStyles])

  // ========== Empty / Error states ==========
  if (query.status === 'error') {
    const err = query.error
    if (err instanceof MarketApiError) {
      if (err.kind === 'not-found') return <EmptyKline reason="not-found" />
      if (err.kind === 'unavailable' || err.kind === 'bad-gateway') {
        return <EmptyKline reason="unavailable" onRetry={() => void query.refetch()} />
      }
    }
    return <EmptyKline reason="unavailable" onRetry={() => void query.refetch()} />
  }

  if (query.status === 'success' && query.data.items.length === 0) {
    return <EmptyKline reason="empty" onSwitchToDaily={onSwitchToDaily} />
  }

  return <div ref={containerRef} className="h-full w-full min-h-[400px] bg-cream" />
}
