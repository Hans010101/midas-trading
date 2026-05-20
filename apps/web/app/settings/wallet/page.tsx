'use client'

/**
 * /settings/wallet · 三市场虚拟资金设置页 · 0008 v2 § 7。
 *
 * - 三张卡(A 股 / 美股 / 加密)各自货币符号
 * - 未激活 → 灰色「未设置」+ 激活并保存按钮
 * - 已激活 → 「✓ 已激活」+ 可用余额 + 持仓笔数 + 重置按钮(二次确认)
 * - 重置:清活仓 + 清快照 · 保留订单 + 历史持仓(0008 § 5)
 */

import { useState } from 'react'
import { toast } from 'sonner'

import { TopNav } from '@/components/layout/top-nav'
import { VirtualBadge } from '@/components/ui/virtual-badge'
import {
  useAccount,
  useActivateAccount,
  usePositions,
} from '@/hooks/use-virtual'
import {
  CURRENCY_SYMBOL,
  MARKET_LABEL,
  currencyOf,
  formatMoney,
} from '@/lib/format-money'
import { cn } from '@/lib/utils'
import { MARKETS, type Market } from '@midas/shared'

const MARKET_EMOJI: Record<Market, string> = {
  cn: '🇨🇳',
  us: '🇺🇸',
  crypto: '₿',
}

export default function WalletSettingsPage() {
  return (
    <div className="flex min-h-screen flex-col bg-background">
      <TopNav />
      <main className="mx-auto w-full max-w-4xl px-6 py-10">
        <div className="mb-6 flex items-center gap-3">
          <h1 className="font-serif text-2xl font-bold text-foreground">
            虚拟资金设置
          </h1>
          <VirtualBadge size="sm" />
        </div>
        <p className="mb-8 text-sm text-muted-foreground">
          三个市场各用各的货币,绝不折算合计 · 没设置的市场无法下单
        </p>

        <div className="space-y-4">
          {MARKETS.map((m) => (
            <WalletCard key={m} market={m} />
          ))}
        </div>

        <p className="mt-10 text-center text-xs text-muted-foreground/70">
          模拟交易,不构成投资建议
        </p>
      </main>
    </div>
  )
}

interface WalletCardProps {
  market: Market
}

function WalletCard({ market }: WalletCardProps) {
  const currency = currencyOf(market)
  const { data: account, isLoading } = useAccount(market)
  const { data: positions = [] } = usePositions({ market, includeClosed: false })
  const activateMutation = useActivateAccount()

  const [input, setInput] = useState('')
  const [showConfirm, setShowConfirm] = useState(false)

  const isActivated = account !== null && account !== undefined
  const activePositionCount = positions.length

  async function handleActivateOrReset() {
    if (!input.trim()) {
      toast.error('请填写初始资金金额')
      return
    }
    const amount = Number(input)
    if (!Number.isFinite(amount) || amount <= 0) {
      toast.error('金额必须是正数')
      return
    }
    if (amount > 999_999_999) {
      toast.error('单市场金额上限 9.99 亿')
      return
    }

    if (isActivated) {
      // 已激活 → 二次确认
      setShowConfirm(true)
      return
    }

    try {
      await activateMutation.mutateAsync({
        market,
        initialCapital: input.trim(),
      })
      toast.success(
        `${MARKET_LABEL[market]} 已激活 · ${formatMoney(input.trim(), currency)}`,
        { className: 'midas-toast-success' },
      )
      setInput('')
    } catch (e) {
      const msg = e instanceof Error ? e.message : '激活失败'
      toast.error(msg)
    }
  }

  async function confirmReset() {
    setShowConfirm(false)
    try {
      await activateMutation.mutateAsync({
        market,
        initialCapital: input.trim(),
      })
      toast.success(
        `${MARKET_LABEL[market]} 已重置 · ${formatMoney(input.trim(), currency)}`,
        { className: 'midas-toast-success' },
      )
      setInput('')
    } catch (e) {
      const msg = e instanceof Error ? e.message : '重置失败'
      toast.error(msg)
    }
  }

  return (
    <div
      className={cn(
        'rounded-lg border bg-cream p-6 shadow-sm',
        isActivated ? 'border-paper' : 'border-paper',
      )}
    >
      <div className="mb-3 flex items-center gap-2">
        <span className="text-xl" aria-hidden="true">
          {MARKET_EMOJI[market]}
        </span>
        <h2 className="font-serif text-lg font-bold text-foreground">
          {MARKET_LABEL[market]} · {currency}
        </h2>
      </div>

      <div className="mb-4 flex items-center gap-3">
        <div className="relative flex-1">
          <span className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 font-mono text-sm text-muted-foreground">
            {currency === 'USDT' ? '' : CURRENCY_SYMBOL[currency]}
          </span>
          <input
            type="number"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder={isActivated ? '改金额会重置该市场' : `输入初始资金`}
            min={1}
            max={999_999_999}
            className={cn(
              'h-10 w-full rounded-md border border-paper bg-background font-mono text-base text-foreground placeholder:text-muted-foreground/50',
              currency === 'USDT' ? 'pl-3 pr-12' : 'pl-7 pr-3',
            )}
          />
          {currency === 'USDT' && (
            <span className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 font-mono text-xs text-muted-foreground">
              USDT
            </span>
          )}
        </div>

        <button
          type="button"
          onClick={handleActivateOrReset}
          disabled={activateMutation.isPending}
          className={cn(
            'rounded-md px-4 py-2 text-sm font-medium transition-colors',
            isActivated
              ? 'border border-midas-red text-midas-red hover:bg-midas-red-glow'
              : 'bg-midas-red text-white hover:bg-midas-red-deep',
          )}
        >
          {activateMutation.isPending
            ? '提交中…'
            : isActivated
              ? '重置该市场'
              : '激活并保存'}
        </button>
      </div>

      {isLoading ? (
        <p className="text-xs text-muted-foreground/60">载入中…</p>
      ) : isActivated ? (
        <div className="space-y-1 text-xs text-muted-foreground">
          <p className="text-bull">
            ✓ 已激活 · 初始 {formatMoney(account.initial_capital, currency)}
          </p>
          <p>
            可用 {formatMoney(account.cash_balance, currency)} · 持仓{' '}
            {activePositionCount} 笔 · 累计已实现{' '}
            <span
              className={cn(
                'font-mono',
                Number(account.realized_pnl) > 0 && 'text-bull',
                Number(account.realized_pnl) < 0 && 'text-bear',
              )}
            >
              {formatMoney(account.realized_pnl, currency, { sign: true })}
            </span>
          </p>
        </div>
      ) : (
        <p className="text-xs text-warn">
          ⚠ 未设置 · 设置后才能在 {MARKET_LABEL[market]} 下单
        </p>
      )}

      {showConfirm && (
        <ResetConfirmDialog
          market={market}
          currency={currency}
          newAmount={input}
          onConfirm={confirmReset}
          onCancel={() => setShowConfirm(false)}
        />
      )}
    </div>
  )
}

interface ResetConfirmProps {
  market: Market
  currency: ReturnType<typeof currencyOf>
  newAmount: string
  onConfirm: () => void
  onCancel: () => void
}

function ResetConfirmDialog({
  market, currency, newAmount, onConfirm, onCancel,
}: ResetConfirmProps) {
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-foreground/40 p-4"
      role="dialog"
      aria-modal="true"
    >
      <div className="w-full max-w-md rounded-lg border border-midas-red bg-cream p-6 shadow-lg">
        <h3 className="mb-2 font-serif text-lg font-bold text-foreground">
          重置{MARKET_LABEL[market]}虚拟资金?
        </h3>
        <p className="mb-4 text-sm text-foreground">
          这会清空该市场的:
        </p>
        <ul className="mb-4 list-inside list-disc space-y-1 text-sm text-muted-foreground">
          <li>当前持仓(活仓全部清零)</li>
          <li>权益曲线快照</li>
          <li>账户余额改为 {formatMoney(newAmount, currency)}</li>
        </ul>
        <p className="mb-6 text-xs text-muted-foreground/80">
          订单流水 + 历史持仓会保留 · 你可以在我的账户页查看复盘
        </p>
        <div className="flex justify-end gap-2">
          <button
            type="button"
            onClick={onCancel}
            className="rounded-md border border-paper bg-background px-4 py-2 text-sm text-foreground hover:bg-cream"
          >
            取消
          </button>
          <button
            type="button"
            onClick={onConfirm}
            className="rounded-md bg-midas-red px-4 py-2 text-sm font-medium text-white hover:bg-midas-red-deep"
          >
            确认重置
          </button>
        </div>
      </div>
    </div>
  )
}
