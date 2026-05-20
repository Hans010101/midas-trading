'use client'

/**
 * 工作台全局状态(Zustand)。
 *
 * - market / symbol / period:K 线工作台的选中状态,持久化到 localStorage
 * - indicators:MA / MACD / RSI / BOLL 四个指标的开关,持久化
 *
 * 用 immer 写可变 setter 语法,用 persist 跨页存活。
 * skipHydration=true + 由 Provider 在 mount 后 rehydrate(避免 SSR 阶段访问 localStorage)。
 */

import { create } from 'zustand'
import { createJSONStorage, persist } from 'zustand/middleware'
import { immer } from 'zustand/middleware/immer'
import type { Market, Period } from '@midas/shared'

export const DEFAULT_SYMBOLS_BY_MARKET: Record<Market, string> = {
  cn: '600519',
  us: 'NVDA',
  crypto: 'BTC/USDT',
}

/** 当前市场可选的 demo 标的列表(M0 写死,Task 4 完整自选股) */
export const DEMO_SYMBOLS_BY_MARKET: Record<Market, ReadonlyArray<{ symbol: string; name: string }>> = {
  cn: [{ symbol: '600519', name: '贵州茅台' }],
  us: [{ symbol: 'NVDA', name: 'NVIDIA' }],
  crypto: [{ symbol: 'BTC/USDT', name: 'Bitcoin' }],
}

export type IndicatorName = 'MA' | 'MACD' | 'RSI' | 'BOLL'

interface WorkbenchState {
  market: Market
  symbol: string
  period: Period
  indicators: Record<IndicatorName, boolean>
  /** 缠论标注层开关 · 默认关 · 0011 ADR § 7 */
  chanEnabled: boolean
}

interface WorkbenchActions {
  setMarket: (m: Market) => void
  setSymbol: (s: string) => void
  setPeriod: (p: Period) => void
  toggleIndicator: (name: IndicatorName) => void
  toggleChan: () => void
}

export type WorkbenchStore = WorkbenchState & WorkbenchActions

export const useWorkbenchStore = create<WorkbenchStore>()(
  persist(
    immer((set) => ({
      market: 'crypto',
      symbol: 'BTC/USDT',
      period: '1d',
      indicators: { MA: true, MACD: false, RSI: false, BOLL: false },
      chanEnabled: false,
      setMarket: (m) =>
        set((state) => {
          state.market = m
          // 切换市场 → 自动跳到该市场默认 demo 标的
          state.symbol = DEFAULT_SYMBOLS_BY_MARKET[m]
        }),
      setSymbol: (s) =>
        set((state) => {
          state.symbol = s
        }),
      setPeriod: (p) =>
        set((state) => {
          state.period = p
        }),
      toggleIndicator: (name) =>
        set((state) => {
          state.indicators[name] = !state.indicators[name]
        }),
      toggleChan: () =>
        set((state) => {
          state.chanEnabled = !state.chanEnabled
        }),
    })),
    {
      name: 'midas-workbench',
      storage: createJSONStorage(() =>
        typeof window !== 'undefined' ? window.localStorage : (null as unknown as Storage),
      ),
      skipHydration: true,
    },
  ),
)
