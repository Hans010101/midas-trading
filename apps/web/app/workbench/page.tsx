'use client'

/**
 * /workbench - K 线工作台 · H Checkpoint 完整三栏布局。
 *
 * 布局(响应式桌面优先 ≥1280px,移动端 M3+ 再说):
 *   ┌──────────────────────────────────────────────────────────────┐
 *   │  Header(Logo + 市场 Tab + 用户菜单占位)1px 红色 border       │
 *   ├──────┬───────────────────────────────────────┬───────────────┤
 *   │ 60px │  信号条占位(M1)                       │ 280px         │
 *   │ 工具 ├───────────────────────────────────────┤ 自选股 demo   │
 *   │ 占位 │  symbol + 指标 + 周期 切换 + K 线图   │ ───────────── │
 *   │ M1   │                                        │ AI 决策卡 M1 │
 *   └──────┴───────────────────────────────────────┴───────────────┘
 */

import { useEffect } from 'react'

import { TopNav } from '@/components/layout/top-nav'
import { ChartArea } from '@/components/workbench/chart-area'
import { Header } from '@/components/workbench/header'
import { ToolBar } from '@/components/workbench/tool-bar'
import { WatchlistColumn } from '@/components/workbench/watchlist-column'
import { useWorkbenchStore } from '@/lib/store/workbench-store'

export default function WorkbenchPage() {
  // skipHydration=true,在 client mount 后手动 rehydrate(避免 SSR 阶段访问 localStorage)
  useEffect(() => {
    void useWorkbenchStore.persist.rehydrate()
  }, [])

  return (
    <div className="flex h-screen flex-col bg-background">
      <TopNav />
      <Header />
      <div className="flex flex-1 overflow-hidden">
        <ToolBar />
        <ChartArea />
        <WatchlistColumn />
      </div>
    </div>
  )
}
