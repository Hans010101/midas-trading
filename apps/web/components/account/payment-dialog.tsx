'use client'

/**
 * 会员订阅支付弹层(Phase 2a · OxaPay 托管收款)· 选档后:建单 → 跳转托管收款页 → 到账轮询 → 成功开 Pro。
 *
 * 🔴 红线:前端只建单 + 跳转 OxaPay 托管页 + 查状态;开权益由后端回调 HMAC 验签核验(防伪造多重)·
 * 前端不判付款真伪。托管页由 OxaPay 处理链/币选择与确认,无需前端展示地址/二维码。
 */

import { useQueryClient } from '@tanstack/react-query'
import { Check, ExternalLink, Loader2 } from 'lucide-react'
import { useEffect, useRef } from 'react'
import { toast } from 'sonner'

import { QUOTA_QUERY_KEY } from '@/hooks/use-quota'
import { useCreatePaymentOrder, useOrderStatus } from '@/hooks/use-payment'
import { PaymentApiError, type Period } from '@/lib/api/payment'
import { PLAN_TIERS } from '@/lib/payment-plans'
import { cn } from '@/lib/utils'

export function PaymentDialog({
  period, onClose,
}: {
  period: Period
  onClose: () => void
}) {
  const tier = PLAN_TIERS.find((t) => t.period === period)
  const create = useCreatePaymentOrder()
  const qc = useQueryClient()
  const startedRef = useRef(false)
  const openedRef = useRef(false)

  // 弹层打开即建单(只发一次)· StrictMode 双调用由 ref 守住
  useEffect(() => {
    if (startedRef.current) return
    startedRef.current = true
    create.mutate(period)
  }, [create, period])

  const order = create.data ?? null
  const statusQ = useOrderStatus(order?.external_id ?? null)
  const paid = statusQ.data?.status === 'paid'

  // 建单成功 → 自动在新标签打开 OxaPay 托管收款页(只开一次)· 弹窗被拦截时用下方按钮兜底
  useEffect(() => {
    if (order?.payment_url && !openedRef.current) {
      openedRef.current = true
      window.open(order.payment_url, '_blank', 'noopener,noreferrer')
    }
  }, [order])

  // 到账 → 刷新额度(plan 即时变 pro)+ 成功 toast
  useEffect(() => {
    if (paid) {
      void qc.invalidateQueries({ queryKey: QUOTA_QUERY_KEY })
      toast.success('Pro 已开通 · 感谢支持点金', { className: 'midas-toast-success', duration: 5000 })
    }
  }, [paid, qc])

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-foreground/40 p-4"
      role="dialog"
      aria-modal="true"
      onClick={(e) => { if (e.target === e.currentTarget) onClose() }}
    >
      <div className="w-full max-w-md rounded-lg border border-gold/60 bg-cream p-6 shadow-xl">
        <h3 className="mb-1 text-center font-serif text-xl font-bold text-foreground">
          {paid ? 'Pro 已开通' : `开通 Pro · ${tier?.label ?? ''}`}
        </h3>

        {/* 1 · 建单中 */}
        {create.isPending && (
          <div className="flex flex-col items-center gap-3 py-10 text-sm text-muted-foreground">
            <Loader2 className="h-6 w-6 animate-spin text-gold" />
            生成收款单…
          </div>
        )}

        {/* 2 · 建单失败 */}
        {create.isError && (
          <div className="py-8 text-center">
            <p className="mb-4 text-sm text-midas-red">
              {create.error instanceof PaymentApiError ? create.error.detail : '生成收款单失败'}
            </p>
            <button
              type="button"
              onClick={() => create.mutate(period)}
              className="rounded-md border border-midas-red px-4 py-2 text-sm text-midas-red hover:bg-midas-red-glow"
            >
              重试
            </button>
          </div>
        )}

        {/* 3 · 跳转托管收款页 + 到账轮询 */}
        {order && !paid && (
          <>
            <p className="mb-1 mt-3 text-center text-sm text-foreground">
              <span className="font-mono text-lg font-bold">{tier?.priceUsdt}</span>
              <span className="ml-1 text-muted-foreground">USDT</span>
            </p>
            <p className="mb-4 text-center text-xs leading-relaxed text-muted-foreground">
              前往 OxaPay 安全收款页完成付款 · 支持 USDT 等多链(在收款页内选择链与币种)
            </p>

            <a
              href={order.payment_url}
              target="_blank"
              rel="noopener noreferrer"
              className="mb-3 flex w-full items-center justify-center gap-2 rounded-md bg-midas-red px-4 py-2.5 text-sm font-medium text-white transition-colors hover:bg-midas-red-deep"
            >
              <ExternalLink className="h-4 w-4" />
              前往收款页付款
            </a>

            <div className="flex items-center justify-center gap-2 rounded-md bg-gold/10 px-3 py-2.5 text-xs text-gold">
              <Loader2 className="h-4 w-4 animate-spin" />
              等待到账 · 链上确认约几分钟,确认后自动开通(本页可保持打开)
            </div>
            <p className="mt-2 text-center font-mono text-[10px] text-muted-foreground/60">
              订单号 {order.external_id.slice(0, 12)}…
            </p>
          </>
        )}

        {/* 4 · 成功 */}
        {paid && (
          <div className="flex flex-col items-center gap-3 py-8 text-center">
            <div className="flex h-14 w-14 items-center justify-center rounded-full bg-up/15">
              <Check className="h-7 w-7 text-up" />
            </div>
            <p className="text-sm text-foreground">
              {tier?.label} Pro 已开通 · 全部更高额度已生效
            </p>
          </div>
        )}

        <button
          type="button"
          onClick={onClose}
          className={cn(
            'mt-5 w-full rounded-md py-2.5 text-sm font-medium transition-colors',
            paid
              ? 'bg-midas-red text-white hover:bg-midas-red-deep'
              : 'border border-paper bg-background text-foreground hover:bg-cream',
          )}
        >
          {paid ? '完成' : '关闭'}
        </button>
      </div>
    </div>
  )
}
