'use client'

/**
 * 注册用户自动策略页 · /platinum 保留为兼容旧链接。
 *
 * 注册用户可开/关并查看自己的智能/托管独立模拟账户。
 */

import { useState } from 'react'

import { TopNav } from '@/components/layout/top-nav'
import { IntelligentPanel } from '@/components/platinum/intelligent-panel'
import { ManagedPanel } from '@/components/platinum/managed-panel'

type Tab = 'intelligent' | 'managed'

export default function PlatinumSelfPage() {
  const [tab, setTab] = useState<Tab>('intelligent')

  const tabBtn = (key: Tab) =>
    `rounded-md px-4 py-1.5 text-sm font-medium transition-colors ${
      tab === key
        ? 'bg-midas-red text-white'
        : 'border border-paper text-muted-foreground hover:text-foreground'
    }`

  return (
    <div className="flex min-h-screen flex-col bg-background">
      <TopNav />
      <main className="mx-auto w-full max-w-6xl px-6 py-8">
        <div className="mb-1 flex items-center gap-2">
          <h1 className="font-serif text-xl font-bold">我的自动策略</h1>
          <span className="rounded bg-gold/10 px-2 py-0.5 text-[11px] text-gold">注册用户免费</span>
        </div>
        <p className="mb-5 text-sm text-muted-foreground">
          开/关后,系统按策略信号在你的独立账户自动开仓 / 平仓 · 持仓与盈亏实时展示。
        </p>

        <div className="mb-6 flex gap-2">
          <button type="button" onClick={() => setTab('intelligent')} className={tabBtn('intelligent')}>
            智能交易
          </button>
          <button type="button" onClick={() => setTab('managed')} className={tabBtn('managed')}>
            托管交易
          </button>
        </div>

        {tab === 'intelligent' ? <IntelligentPanel /> : <ManagedPanel />}
      </main>
    </div>
  )
}
