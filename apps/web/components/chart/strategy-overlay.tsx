'use client'

/**
 * 策略信号标注层 · 形态A 单元3(ADR 0037 §5.2 · 拍板②③)。
 *
 * 复用现有 midas-fractal overlay(同缠论买卖点 B1/S1 的画法),把策略买卖信号点标在 K 线上:
 * - 买点 → 'B▲' · 朱红 #DC143C · 画在 K 线下方(midas-fractal 对 'B' 开头下偏移)
 * - 卖点 → 'S▼' · 墨绿 #0F6E5F · 画在 K 线上方(midas-fractal 对 'S' 开头上偏移)
 *   买/卖配色与缠论买卖点一致(朱红=涨/买、墨绿=跌/卖),用户零学习成本。
 *
 * ★ 独立 groupId(midas-strategy-overlay),与缠论 overlay(midas-chan-overlay)互不干扰:
 *   - 各自 clear/recreate,可独立开关,缠论标注零回归。
 * ★ 红线:纯展示 · 只读 /strategy-signals · 不下单 / 不自动交易(看完走第一层一键下单)。
 *
 * 全 props 驱动(symbol/market/period/strategy/enabled 都由各主图传入),不依赖 workbench store,
 * 三套主图(工作台 / 现货详情 / 合约详情)统一用同一组件接入。
 */

import type { Chart } from 'klinecharts'
import { useEffect } from 'react'

import { useStrategySignals } from '@/hooks/use-strategy'
import type { Instrument, StrategyKind } from '@/lib/api/strategy'
import { ensureMidasOverlays } from '@/lib/klinecharts-extensions'
import type { Market, Period } from '@midas/shared'

interface Props {
  chart: Chart | null
  symbol: string
  market: Market
  period: Period
  strategy: StrategyKind
  instrument?: Instrument
  enabled?: boolean
}

const STRATEGY_GROUP_ID = 'midas-strategy-overlay'
const COLOR_BUY = '#DC143C' // 朱红 · 买点(同缠论买点 / 产品涨色)
const COLOR_SELL = '#0F6E5F' // 墨绿 · 卖点(同缠论卖点 / 产品跌色)

export function StrategyOverlay({
  chart,
  symbol,
  market,
  period,
  strategy,
  instrument,
  enabled = false,
}: Props) {
  const { data } = useStrategySignals({
    symbol, market, period, strategy, instrument, enabled,
  })

  useEffect(() => {
    if (!chart) return

    // 确保自定义 overlay 已注册(幂等 · 与缠论共用 midas-fractal)
    ensureMidasOverlays()

    // 先清旧策略 overlay(独立 groupId · 不动缠论 midas-chan-overlay)
    try {
      chart.removeOverlay({ groupId: STRATEGY_GROUP_ID } as never)
    } catch {
      /* ignore · 无 overlay */
    }

    if (!enabled || !data) return

    const overlays = data.signals.map((sig) => {
      const isBuy = sig.kind === 'buy'
      return {
        name: 'midas-fractal',
        groupId: STRATEGY_GROUP_ID,
        paneId: 'candle_pane',
        lock: true,
        points: [{ timestamp: new Date(sig.ts).getTime(), value: sig.price }],
        // 'B…' → 下方偏移 / 'S…' → 上方偏移(复用 midas-fractal 既有规则)
        // ① 信号点标触发价(纯数据 · 智能小数:≥1000 整数千分位 · <1000 两位)
        extendData: `${isBuy ? 'B▲' : 'S▼'} ${
          sig.price >= 1000
            ? Math.round(sig.price).toLocaleString('en-US')
            : sig.price.toFixed(2)
        }`,
        styles: {
          text: {
            color: isBuy ? COLOR_BUY : COLOR_SELL,
            size: 12,
            family: 'JetBrains Mono, Consolas, monospace',
            weight: 'bold',
            // midas-fractal 默认蓝底 + padding,必须清零得到「干净文字标记」
            backgroundColor: 'transparent',
            borderColor: 'transparent',
            borderSize: 0,
            paddingLeft: 0,
            paddingRight: 0,
            paddingTop: 0,
            paddingBottom: 0,
          },
        },
      }
    })

    if (overlays.length === 0) return
    try {
      chart.createOverlay(overlays as never)
    } catch (e) {
      console.warn('[strategy-overlay] createOverlay failed:', e)
    }
  }, [chart, enabled, data])

  return null
}
