'use client'

/**
 * 会员订阅支付弹层(Phase 2a 刀2)· 选档后:建单 → 收款地址/二维码/金额 → 到账轮询 → 成功开 Pro。
 *
 * 🔴 红线:前端只建单 + 展示收款 + 查状态;开权益由后端回调核验(防伪造四重)· 前端不判付款真伪。
 * 价格如实(USDT)· BSC 链警示醒目(转错链丢币)。
 */

import { useQueryClient } from '@tanstack/react-query'
import { Check, Copy, Loader2 } from 'lucide-react'
import { QRCodeSVG } from 'qrcode.react'
import { useEffect, useRef, useState } from 'react'
import { toast } from 'sonner'

import { QUOTA_QUERY_KEY } from '@/hooks/use-quota'
import { useCreatePaymentOrder, useOrderStatus } from '@/hooks/use-payment'
import { PaymentApiError, type Period } from '@/lib/api/payment'
import { CHAIN_WARNING, PLAN_TIERS } from '@/lib/payment-plans'
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
  const [copied, setCopied] = useState(false)
  const startedRef = useRef(false)

  // 弹层打开即建单(只发一次)· StrictMode 双调用由 ref 守住
  useEffect(() => {
    if (startedRef.current) return
    startedRef.current = true
    create.mutate(period)
  }, [create, period])

  const order = create.data ?? null
  const statusQ = useOrderStatus(order?.external_id ?? null)
  const paid = statusQ.data?.status === 'paid'

  // 到账 → 刷新额度(plan 即时变 pro)+ 成功 toast
  useEffect(() => {
    if (paid) {
      void qc.invalidateQueries({ queryKey: QUOTA_QUERY_KEY })
      toast.success('Pro 已开通 · 感谢支持点金', { className: 'midas-toast-success', duration: 5000 })
    }
  }, [paid, qc])

  async function copyAddr() {
    if (!order) return
    try {
      await navigator.clipboard.writeText(order.address)
      setCopied(true)
      setTimeout(() => setCopied(false), 1800)
    } catch {
      toast.error('复制失败 · 请手动选择地址')
    }
  }

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
            生成收款地址…
          </div>
        )}

        {/* 2 · 建单失败 */}
        {create.isError && (
          <div className="py-8 text-center">
            <p className="mb-4 text-sm text-midas-red">
              {create.error instanceof PaymentApiError ? create.error.detail : '生成收款地址失败'}
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

        {/* 3 · 收款信息 + 到账轮询 */}
        {order && !paid && (
          <>
            <p className="mb-3 text-center text-sm">
              <span className="font-mono text-lg font-bold text-foreground">{order.payment_amount}</span>
              <span className="ml-1 text-muted-foreground">USDT</span>
            </p>

            <div className="mb-3 flex justify-center rounded-lg bg-white p-3">
              <QRCodeSVG value={order.address} size={160} />
            </div>

            <label className="mb-1 block text-xs text-muted-foreground">收款地址</label>
            <div className="mb-3 flex items-center gap-2">
              <code className="flex-1 break-all rounded border border-paper bg-background px-2 py-1.5 font-mono text-[11px]">
                {order.address}
              </code>
              <button
                type="button"
                onClick={() => void copyAddr()}
                aria-label="复制地址"
                className="shrink-0 rounded border border-paper p-2 text-muted-foreground hover:text-gold"
              >
                {copied ? <Check className="h-4 w-4 text-up" /> : <Copy className="h-4 w-4" />}
              </button>
            </div>

            {/* ★ BSC 链警示(转错链丢币)*/}
            <p className="mb-3 rounded-md border border-midas-red/50 bg-midas-red-glow/40 px-3 py-2 text-xs leading-relaxed text-midas-red">
              ⚠ {CHAIN_WARNING}
            </p>

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
