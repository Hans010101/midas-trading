'use client'

/**
 * 缠论标注层 · 0011 ADR § 6。
 *
 * - 笔 · segment(midas-red-deep #9E1024)
 * - 中枢 · rect(gold #B8860B 半透明)
 * - 分型 · simpleAnnotation ▼/▲(midas-red)
 *
 * 单 useEffect 处理所有状态 · 避免 clear / create 竞态。
 */

import type { Chart } from 'klinecharts'
import { useEffect } from 'react'

import { useChan } from '@/hooks/use-chan'
import { useWorkbenchStore } from '@/lib/store/workbench-store'

interface Props {
  chart: Chart | null
}

const CHAN_GROUP_ID = 'midas-chan-overlay'

export function ChanOverlay({ chart }: Props) {
  const symbol = useWorkbenchStore((s) => s.symbol)
  const market = useWorkbenchStore((s) => s.market)
  const period = useWorkbenchStore((s) => s.period)
  const chanEnabled = useWorkbenchStore((s) => s.chanEnabled)

  const { data } = useChan({
    symbol, market, period,
    enabled: chanEnabled,
  })

  useEffect(() => {
    if (!chart) return

    // 1. 先清旧 chan overlay(幂等)
    try {
      chart.removeOverlay({ groupId: CHAN_GROUP_ID } as never)
    } catch {
      /* ignore · 无 overlay */
    }

    if (!chanEnabled || !data) return

    // 2. 构造 overlay 数组
    const overlays: unknown[] = []

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
        styles: { line: { color: '#9E1024', size: 1.5 } },
      })
    }

    for (const zs of data.zhongshus) {
      overlays.push({
        name: 'rect',
        groupId: CHAN_GROUP_ID,
        paneId: 'candle_pane',
        lock: true,
        points: [
          { timestamp: new Date(zs.start_ts).getTime(), value: zs.high },
          { timestamp: new Date(zs.end_ts).getTime(), value: zs.low },
        ],
        styles: {
          rect: {
            color: 'rgba(184, 134, 11, 0.12)',
            borderColor: '#B8860B',
            borderSize: 1,
            borderStyle: 'dashed',
          },
        },
      })
    }

    for (const fx of data.fractals) {
      const isTop = fx.kind === 'G'
      overlays.push({
        name: 'simpleAnnotation',
        groupId: CHAN_GROUP_ID,
        paneId: 'candle_pane',
        lock: true,
        points: [
          { timestamp: new Date(fx.ts).getTime(), value: fx.price },
        ],
        extendData: isTop ? '▼' : '▲',
        styles: {
          text: {
            color: '#C8102E',
            size: 10,
            offset: isTop ? [0, -10] : [0, 10],
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
