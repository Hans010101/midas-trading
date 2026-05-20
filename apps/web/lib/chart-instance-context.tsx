'use client'

/**
 * 共享 klinecharts chart instance · 0011 ADR 缠论 + 绘图工具栏共用。
 *
 * 作用:KlineChart 在 onChartReady 时把 instance 写进 context,
 * ToolBar / ChanOverlay / 其他需要 chart 实例的组件读取使用。
 */

import type { Chart } from 'klinecharts'
import {
  createContext,
  useContext,
  useState,
  type ReactNode,
} from 'react'

interface ChartInstanceContextValue {
  chart: Chart | null
  setChart: (chart: Chart | null) => void
}

const Ctx = createContext<ChartInstanceContextValue | null>(null)

export function ChartInstanceProvider({ children }: { children: ReactNode }) {
  const [chart, setChart] = useState<Chart | null>(null)
  return <Ctx.Provider value={{ chart, setChart }}>{children}</Ctx.Provider>
}

export function useChartInstance(): ChartInstanceContextValue {
  const v = useContext(Ctx)
  if (!v) {
    throw new Error('useChartInstance must be inside <ChartInstanceProvider>')
  }
  return v
}
