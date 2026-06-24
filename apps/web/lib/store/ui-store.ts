import { createStore } from 'zustand'
import { createJSONStorage, persist } from 'zustand/middleware'
import { immer } from 'zustand/middleware/immer'

import type { StrategyKind } from '@/lib/api/strategy'

/** AI 策略信号默认显示顺序(用户可左右调 · 持久化)· 加新信号在此追加。
 *  ★ extreme 仅 crypto perp 可用 —— 它在此作为"已知键 + 默认末位",
 *  实际是否显示由 strategy-panel 按市场过滤(现货不出)。 */
export const DEFAULT_STRATEGY_ORDER: StrategyKind[] = [
  'ma_cross',
  'rsi_reversal',
  'boll_reversion',
  'macd_cross',
  'kdj_cross',
  'extreme',
]

export interface UiState {
  sidebarOpen: boolean
  /** AI 策略信号显示顺序(用户左右调 · 全页持久化 · 放 ui-store 因其 root 全局 rehydrate,
   *  workbench-store 仅 /workbench rehydrate · detail 页会丢)。 */
  strategyOrder: StrategyKind[]
  /** 「布林做T」标签在策略标签序列里的位置(仅 crypto · 0=首位 · 与 strategyOrder 一样可左右调 + 持久化)。
   *  做T 是独立 view(布林结构)非 StrategyKind,故位置单存一个 index,渲染时插进 strategyOrder。 */
  dottTabPos: number
}

export interface UiActions {
  toggleSidebar: () => void
  setSidebarOpen: (open: boolean) => void
  setStrategyOrder: (order: StrategyKind[]) => void
  setDottTabPos: (pos: number) => void
}

export type UiStore = UiState & UiActions

/**
 * M0 的 UI 状态样板。
 * 中间件:immer(可变 setter 语法) + persist(localStorage 持久化)。
 */
export const createUiStore = () =>
  createStore<UiStore>()(
    persist(
      immer((set) => ({
        sidebarOpen: true,
        strategyOrder: [...DEFAULT_STRATEGY_ORDER],
        dottTabPos: 0, // 布林做T 默认首位
        toggleSidebar: () =>
          set((state) => {
            state.sidebarOpen = !state.sidebarOpen
          }),
        setSidebarOpen: (open) =>
          set((state) => {
            state.sidebarOpen = open
          }),
        setStrategyOrder: (order) =>
          set((state) => {
            state.strategyOrder = order
          }),
        setDottTabPos: (pos) =>
          set((state) => {
            state.dottTabPos = pos
          }),
      })),
      {
        name: 'midas-ui-store',
        storage: createJSONStorage(() =>
          typeof window !== 'undefined' ? window.localStorage : (null as unknown as Storage),
        ),
        skipHydration: true,
      },
    ),
  )

export type UiStoreApi = ReturnType<typeof createUiStore>
