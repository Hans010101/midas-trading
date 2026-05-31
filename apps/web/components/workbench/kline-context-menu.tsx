'use client'

/**
 * K 线图右键菜单 · 0008 v2 § 8.4 第 2 入口(快捷入口)。
 *
 * 跟顶部按钮 + Cmd+B/S 共用 OrderConfirmDialog · 不重写撮合逻辑。
 * 未激活当前市场虚拟资金时,买/卖菜单项 disabled(跟顶部按钮一致)。
 *
 * 实装方式:
 * - 自管 onContextMenu + position state(避 radix ContextMenu Root 不支持
 *   controlled open · klinecharts canvas 也可能吃事件)
 * - 用 fixed 定位 popover div · 视觉沿用 shadcn ContextMenu 同款米白卡 + 中国红
 * - 点击外部 / Esc 自动关闭
 */

import { ShoppingCart, TrendingDown } from 'lucide-react'
import { useEffect, useRef, useState, type ReactNode } from 'react'

import { OrderConfirmDialog } from '@/components/workbench/order-confirm-dialog'
import { useRequireAuth } from '@/hooks/use-require-auth'
import { useAccount } from '@/hooks/use-virtual'
import { MARKET_LABEL } from '@/lib/format-money'
import { useWorkbenchStore } from '@/lib/store/workbench-store'
import { cn } from '@/lib/utils'

interface Props {
  children: ReactNode
}

interface MenuState {
  open: boolean
  x: number
  y: number
}

export function KlineContextMenu({ children }: Props) {
  const symbol = useWorkbenchStore((s) => s.symbol)
  const market = useWorkbenchStore((s) => s.market)
  const { data: account } = useAccount(market)
  const { requireAuth, isAuthenticated } = useRequireAuth()
  const isActivated = account !== null && account !== undefined

  const [menu, setMenu] = useState<MenuState>({ open: false, x: 0, y: 0 })
  const [dialog, setDialog] = useState<{
    open: boolean
    side: 'buy' | 'sell'
  }>({ open: false, side: 'buy' })

  const menuRef = useRef<HTMLDivElement | null>(null)

  function handleContextMenu(e: React.MouseEvent<HTMLDivElement>) {
    e.preventDefault()
    setMenu({ open: true, x: e.clientX, y: e.clientY })
  }

  function close() {
    setMenu((m) => ({ ...m, open: false }))
  }

  // Outside click + Esc 关闭
  useEffect(() => {
    if (!menu.open) return
    function onDocClick(e: MouseEvent) {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        close()
      }
    }
    function onKey(e: KeyboardEvent) {
      if (e.key === 'Escape') close()
    }
    // 用 setTimeout 推迟一帧,避免本次 contextmenu 的 mousedown 立即触发关闭
    const id = setTimeout(() => {
      document.addEventListener('mousedown', onDocClick)
      document.addEventListener('keydown', onKey)
    }, 0)
    return () => {
      clearTimeout(id)
      document.removeEventListener('mousedown', onDocClick)
      document.removeEventListener('keydown', onKey)
    }
  }, [menu.open])

  function pickBuy() {
    close()
    if (!requireAuth('下单')) return
    setDialog({ open: true, side: 'buy' })
  }

  function pickSell() {
    close()
    if (!requireAuth('下单')) return
    setDialog({ open: true, side: 'sell' })
  }

  return (
    <>
      <div onContextMenu={handleContextMenu} className="contents">
        {children}
      </div>

      {menu.open && (
        <div
          ref={menuRef}
          role="menu"
          aria-label="K 线下单菜单"
          className="fixed z-50 w-56 overflow-hidden rounded-md border border-paper bg-cream shadow-xl"
          style={{ left: menu.x, top: menu.y }}
        >
          <div className="border-b border-paper px-3 py-2 font-mono text-xs text-muted-foreground">
            {symbol} · {MARKET_LABEL[market]}
          </div>
          {!isAuthenticated && (
            <div className="border-b border-paper bg-surface-card px-3 py-2 text-[10px] text-warn">
              ⚠ 未登录 · 点击下单将引导登录
            </div>
          )}
          {isAuthenticated && !isActivated && (
            <div className="border-b border-paper bg-surface-card px-3 py-2 text-[10px] text-warn">
              ⚠ 未设置 {MARKET_LABEL[market]} 账户资金 · 去 /account 激活
            </div>
          )}
          <MenuItem
            // 未登录 · 让用户能点 · 触发引导 / 已登录但未激活 · 禁用
            disabled={isAuthenticated && !isActivated}
            onClick={pickBuy}
            icon={<ShoppingCart className="h-3.5 w-3.5" />}
            label={`买入 ${symbol}`}
          />
          <MenuItem
            disabled={isAuthenticated && !isActivated}
            onClick={pickSell}
            icon={<TrendingDown className="h-3.5 w-3.5" />}
            label={`卖出 ${symbol}`}
          />
          <div className="border-t border-paper px-3 py-1.5 text-[10px] text-muted-foreground/60">
            或:顶部按钮 / ⌘B 买 / ⌘S 卖
          </div>
        </div>
      )}

      <OrderConfirmDialog
        open={dialog.open}
        onClose={() => setDialog({ ...dialog, open: false })}
        symbol={symbol}
        market={market}
        side={dialog.side}
      />
    </>
  )
}

interface MenuItemProps {
  disabled: boolean
  onClick: () => void
  icon: ReactNode
  label: string
}

function MenuItem({ disabled, onClick, icon, label }: MenuItemProps) {
  return (
    <button
      type="button"
      disabled={disabled}
      onClick={onClick}
      role="menuitem"
      className={cn(
        'flex w-full items-center gap-2 px-3 py-2 text-left text-sm transition-colors',
        disabled
          ? 'cursor-not-allowed text-muted-foreground/40'
          : 'text-midas-red hover:bg-midas-red-glow',
      )}
    >
      {icon}
      {label}
    </button>
  )
}
