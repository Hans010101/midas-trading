'use client'

/**
 * 工作台 Header(市场 Tab + 钱包指示 + 买卖按钮)· 0008 v2 § 8。
 *
 * Layout:
 *   [A 股 美股 加密]  |  可用 ¥XXX  持仓 ¥YY  累计盈亏  |  [买入][卖出]
 *
 * 「当前市场 = 当前钱包」· market Tab 切换时,顶部数字跟着切货币。
 * 该市场未激活 → 显示「未设置」+ 跳设置链接;买卖按钮 disabled。
 */

import Link from 'next/link'
import { useEffect, useState } from 'react'

import { OrderConfirmDialog } from '@/components/workbench/order-confirm-dialog'
import { useRequireAuth } from '@/hooks/use-require-auth'
import { useAccount, usePortfolio } from '@/hooks/use-virtual'
import { currencyOf, formatMoney, MARKET_LABEL } from '@/lib/format-money'
import { useWorkbenchStore } from '@/lib/store/workbench-store'
import { cn } from '@/lib/utils'
import type { Market } from '@midas/shared'

export function Header() {
  const market = useWorkbenchStore((s) => s.market)
  const symbol = useWorkbenchStore((s) => s.symbol)

  const { requireAuth, isAuthenticated, isAuthLoading } = useRequireAuth()
  const { data: account } = useAccount(market)
  const { data: portfolio } = usePortfolio()
  const summary = portfolio?.find((s) => s.market === market)

  const [orderDialog, setOrderDialog] = useState<{
    open: boolean
    side: 'buy' | 'sell'
  }>({ open: false, side: 'buy' })

  const isActivated = account !== null && account !== undefined

  // Cmd+B 买 / Cmd+S 卖 全局快捷键(老手入口 · 0008 v2 § 8.4 第 3 种入口)
  // 未登录时也响应快捷键 · 触发登录引导
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      const tag = (e.target as HTMLElement)?.tagName
      if (tag === 'INPUT' || tag === 'TEXTAREA') return
      const isBuy = (e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'b'
      const isSell = (e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 's'
      if (!isBuy && !isSell) return
      e.preventDefault()
      if (!requireAuth('下单')) return
      if (!isActivated) return            // 已登录但未激活 · DisabledTradeButtons 已提示
      setOrderDialog({ open: true, side: isBuy ? 'buy' : 'sell' })
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [isActivated, requireAuth])

  return (
    <header className="h-14 shrink-0 border-b border-midas-red bg-background">
      <div className="flex h-full items-center justify-between gap-4 px-6">
        {/* 钱包指示(随 market 切换)· 市场 Tab 已上移到全站 TopNav(2026-06 顶栏重构)*/}
        <WalletIndicator
          market={market}
          isActivated={isActivated}
          isAuthenticated={isAuthenticated}
          isAuthLoading={isAuthLoading}
          summary={summary}
        />

        {/* 右侧:买卖按钮 */}
        <div className="flex items-center gap-2">
          {isAuthLoading ? (
            <>
              <button type="button" disabled className="rounded-md bg-midas-red/30 px-4 py-1.5 text-sm font-medium text-white/70">
                买入
              </button>
              <button type="button" disabled className="rounded-md border border-midas-red/30 px-4 py-1.5 text-sm font-medium text-midas-red/40">
                卖出
              </button>
            </>
          ) : !isAuthenticated ? (
            // 未登录 · 按钮可点击 · 触发登录引导(M1 第三波 · 匿名 /workbench)
            <>
              <button
                type="button"
                onClick={() => requireAuth('下单')}
                className="rounded-md bg-midas-red px-4 py-1.5 text-sm font-medium text-white shadow-sm transition-colors hover:bg-midas-red-deep"
              >
                买入
              </button>
              <button
                type="button"
                onClick={() => requireAuth('下单')}
                className="rounded-md border border-midas-red bg-background px-4 py-1.5 text-sm font-medium text-midas-red transition-colors hover:bg-midas-red-glow"
              >
                卖出
              </button>
            </>
          ) : isActivated ? (
            <>
              <button
                type="button"
                onClick={() => setOrderDialog({ open: true, side: 'buy' })}
                className="rounded-md bg-midas-red px-4 py-1.5 text-sm font-medium text-white shadow-sm transition-colors hover:bg-midas-red-deep"
              >
                买入
              </button>
              <button
                type="button"
                onClick={() => setOrderDialog({ open: true, side: 'sell' })}
                className="rounded-md border border-midas-red bg-background px-4 py-1.5 text-sm font-medium text-midas-red transition-colors hover:bg-midas-red-glow"
              >
                卖出
              </button>
            </>
          ) : (
            <DisabledTradeButtons market={market} />
          )}
        </div>
      </div>

      <OrderConfirmDialog
        open={orderDialog.open}
        onClose={() => setOrderDialog({ ...orderDialog, open: false })}
        symbol={symbol}
        market={market}
        side={orderDialog.side}
      />
    </header>
  )
}

interface WalletIndicatorProps {
  market: Market
  isActivated: boolean
  isAuthenticated: boolean
  isAuthLoading: boolean
  summary?: { cash_balance: string; positions_value: string; realized_pnl: string }
}

function WalletIndicator({
  market, isActivated, isAuthenticated, isAuthLoading, summary,
}: WalletIndicatorProps) {
  const currency = currencyOf(market)
  if (isAuthLoading) {
    return <div className="text-xs text-muted-foreground/60">正在恢复登录状态…</div>
  }
  if (!isAuthenticated) {
    return (
      <div className="flex items-center gap-2 text-xs text-muted-foreground/70">
        <span>未登录 · 仅看图模式</span>
        <Link
          href="/login"
          className="text-midas-red hover:underline"
        >
          [登录 / 注册]
        </Link>
      </div>
    )
  }
  if (!isActivated) {
    return (
      <div className="flex items-center gap-2 text-xs">
        <span className="text-warn">⚠ 未设置 {MARKET_LABEL[market]} 账户资金</span>
        <Link
          href="/account"
          className="text-midas-red hover:underline"
        >
          [去设置]
        </Link>
      </div>
    )
  }
  if (!summary) {
    return <div className="text-xs text-muted-foreground/60">载入中…</div>
  }
  const realized = Number(summary.realized_pnl)
  return (
    <div className="flex items-center gap-4 font-mono text-xs">
      <Stat label="可用">{formatMoney(summary.cash_balance, currency)}</Stat>
      <Stat label="持仓">{formatMoney(summary.positions_value, currency)}</Stat>
      <Stat label="累计盈亏">
        <span
          className={cn(
            realized > 0 && 'text-up',
            realized < 0 && 'text-down',
          )}
        >
          {formatMoney(summary.realized_pnl, currency, { sign: true })}
        </span>
      </Stat>
    </div>
  )
}

function Stat({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-center gap-1">
      <span className="text-muted-foreground/70">{label}</span>
      <span className="text-foreground">{children}</span>
    </div>
  )
}

function DisabledTradeButtons({ market }: { market: Market }) {
  return (
    <div className="flex items-center gap-2">
      <Link
        href="/account"
        title={`请先设置 ${MARKET_LABEL[market]} 账户资金`}
        className="rounded-md bg-midas-red/30 px-4 py-1.5 text-sm font-medium text-white/70 cursor-not-allowed"
        aria-disabled="true"
      >
        买入
      </Link>
      <Link
        href="/account"
        title={`请先设置 ${MARKET_LABEL[market]} 账户资金`}
        className="rounded-md border border-midas-red/30 bg-background px-4 py-1.5 text-sm font-medium text-midas-red/40 cursor-not-allowed"
        aria-disabled="true"
      >
        卖出
      </Link>
    </div>
  )
}
