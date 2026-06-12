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

import Link from 'next/link'
import { useEffect } from 'react'

import { TopNav } from '@/components/layout/top-nav'
import { ChartArea } from '@/components/workbench/chart-area'
import { Header } from '@/components/workbench/header'
import { ToolBar } from '@/components/workbench/tool-bar'
import { WatchlistColumn } from '@/components/workbench/watchlist-column'
import { ChartInstanceProvider } from '@/lib/chart-instance-context'
import { useWorkbenchStore } from '@/lib/store/workbench-store'

export default function WorkbenchPage() {
  // skipHydration=true,在 client mount 后手动 rehydrate(避免 SSR 阶段访问 localStorage)
  useEffect(() => {
    void useWorkbenchStore.persist.rehydrate()
  }, [])

  return (
    <ChartInstanceProvider>
      <div className="flex h-screen flex-col bg-background">
        <TopNav />

        {/* 移动刀C:窄屏降级(三栏在 375px 挤压成竖条不可用 · 审计 M3)——
            引导走 市场页 → 详情页 移动流;lg+ 工作台完全不受影响。 */}
        <div className="flex flex-1 flex-col items-center justify-center gap-4 px-6 text-center lg:hidden">
          <h1 className="font-serif text-xl font-bold text-foreground">交易工作台建议桌面访问</h1>
          <p className="max-w-sm text-sm leading-relaxed text-muted-foreground">
            工作台为多栏专业布局,小屏体验不佳。手机端可在各市场页选标的进详情页,
            看 K 线 / AI 决策卡 / 虚拟下单,功能一致。
          </p>
          <div className="flex gap-3">
            <Link
              href="/global"
              className="rounded-md bg-midas-red px-4 py-2 text-sm font-medium text-white hover:bg-midas-red-deep"
            >
              去全球市场
            </Link>
            <Link
              href="/crypto-market"
              className="rounded-md border border-midas-red px-4 py-2 text-sm text-midas-red hover:bg-midas-red-glow"
            >
              去加密市场
            </Link>
          </div>
        </div>

        {/* lg+ 原三栏工作台(零变化) */}
        <div className="hidden flex-1 flex-col overflow-hidden lg:flex">
          <Header />
          <div className="flex flex-1 overflow-hidden">
            <ToolBar />
            <ChartArea />
            <WatchlistColumn />
          </div>
        </div>
      </div>
    </ChartInstanceProvider>
  )
}
