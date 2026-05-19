import { createStore } from 'zustand'
import { createJSONStorage, persist } from 'zustand/middleware'
import { immer } from 'zustand/middleware/immer'

export interface UiState {
  sidebarOpen: boolean
}

export interface UiActions {
  toggleSidebar: () => void
  setSidebarOpen: (open: boolean) => void
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
        toggleSidebar: () =>
          set((state) => {
            state.sidebarOpen = !state.sidebarOpen
          }),
        setSidebarOpen: (open) =>
          set((state) => {
            state.sidebarOpen = open
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
