'use client'

import { createContext, useContext, useEffect, useRef, type ReactNode } from 'react'
import { useStore } from 'zustand'

import { createUiStore, type UiStore, type UiStoreApi } from './ui-store'

const UiStoreContext = createContext<UiStoreApi | null>(null)

/**
 * Next.js App Router SSR-safe Zustand Provider 样板。
 * 在客户端 mount 后触发 rehydrate(避免 SSR 阶段访问 localStorage)。
 */
export function UiStoreProvider({ children }: { children: ReactNode }) {
  const storeRef = useRef<UiStoreApi | null>(null)
  if (storeRef.current === null) {
    storeRef.current = createUiStore()
  }

  useEffect(() => {
    void storeRef.current?.persist.rehydrate()
  }, [])

  return <UiStoreContext.Provider value={storeRef.current}>{children}</UiStoreContext.Provider>
}

export function useUiStore<T>(selector: (store: UiStore) => T): T {
  const store = useContext(UiStoreContext)
  if (!store) {
    throw new Error('useUiStore must be used within <UiStoreProvider>')
  }
  return useStore(store, selector)
}
