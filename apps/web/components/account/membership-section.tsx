'use client'

/**
 * 会员订阅区(/account/membership)· 当前档 + 月/季/年 + 兑换码(第 4 框)+ 权益对比 + 客服。
 *
 * 价格如实(USDT)· 已是 Pro 显到期日 + 续费;免费版引导升级。开权益由后端回调核验。
 * 标题保留「会员 · 支持者计划」· 描述段/自动回落行已删;兑换码整合自原 RedeemCard(复用 /redeem 逻辑)。
 */

import { useMutation } from '@tanstack/react-query'
import { Check, Sparkles, Ticket } from 'lucide-react'
import { useSession } from 'next-auth/react'
import { useState } from 'react'
import { toast } from 'sonner'

import { useInvalidateQuota, useQuota } from '@/hooks/use-quota'
import { type Period } from '@/lib/api/payment'
import { RedeemApiError, redeemCode } from '@/lib/api/redeem'
import {
  monthlyEquivalent,
  PLAN_TIERS,
  PRO_BENEFITS,
  savingsPct,
} from '@/lib/payment-plans'
import { redeemErrorText, redeemSuccessText } from '@/lib/redeem-view'
import { cn } from '@/lib/utils'

import { PaymentDialog } from './payment-dialog'
import { SupportTicketDialog } from './support-ticket-dialog'

function fmtDate(iso: string | null): string {
  if (!iso) return '—'
  const d = new Date(iso)
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

export function MembershipSection() {
  const { data: quota } = useQuota()
  const [payPeriod, setPayPeriod] = useState<Period | null>(null)
  const [showSupport, setShowSupport] = useState(false)

  const isPro = quota?.plan === 'pro'
  const cta = isPro ? '续费' : '开通'

  return (
    <div className="space-y-6">
      {/* 标题(支持者计划描述段已删 · 直接接套餐框)*/}
      <h2 className="font-serif text-xl font-bold text-foreground">会员 · 支持者计划</h2>

      {/* 当前档位 */}
      <div className="flex items-center justify-between rounded-lg border border-paper bg-surface-card px-4 py-3">
        <span className="text-sm text-muted-foreground">当前会员</span>
        {isPro ? (
          <span className="font-mono text-sm text-gold">
            Pro · 到期 {fmtDate(quota?.plan_expires_at ?? null)}
          </span>
        ) : (
          <span className="font-mono text-sm text-muted-foreground">免费版</span>
        )}
      </div>

      {/* 三档定价 + 兑换码(真 4 框横排 · 宽屏 4 / 中屏 2×2 / 窄屏堆叠)*/}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {PLAN_TIERS.map((t) => {
          const save = savingsPct(t)
          return (
            <div
              key={t.period}
              className={cn(
                'flex flex-col rounded-2xl border bg-background p-5 shadow-sm',
                t.highlight ? 'border-2 border-gold/60' : 'border-paper',
              )}
            >
              <div className="flex items-center justify-between">
                <span className="font-serif text-base font-bold">{t.label}</span>
                {t.highlight && (
                  <span className="rounded-full bg-gold/10 px-2 py-0.5 text-[10px] font-medium text-gold">
                    最划算
                  </span>
                )}
              </div>
              <div className="mt-3">
                <span className="font-mono text-2xl font-bold text-foreground">{t.priceUsdt}</span>
                <span className="ml-1 text-xs text-muted-foreground">USDT</span>
              </div>
              <p className="mt-1 text-[11px] text-muted-foreground/70">
                月均 {monthlyEquivalent(t)} USDT
                {save > 0 && <span className="ml-1 text-midas-red">· 省 {save}%</span>}
              </p>
              <button
                type="button"
                onClick={() => setPayPeriod(t.period)}
                className={cn(
                  'mt-4 rounded-md py-2 text-sm font-medium transition-colors',
                  t.highlight
                    ? 'bg-midas-red text-white hover:bg-midas-red-deep'
                    : 'border border-midas-red text-midas-red hover:bg-midas-red-glow',
                )}
              >
                {cta} Pro
              </button>
            </div>
          )
        })}
        {/* 第 4 框 · 兑换码(与套餐框同尺寸 · 复用 /redeem 兑换逻辑)*/}
        <RedeemPlanCard />
      </div>

      {/* Pro 权益对比 */}
      <div className="rounded-lg border border-paper bg-surface-card p-4">
        <div className="mb-3 flex items-center gap-1.5 text-sm font-medium text-foreground">
          <Sparkles className="h-4 w-4 text-gold" /> Pro 解锁更高额度
        </div>
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-paper text-xs text-muted-foreground">
              <th className="py-1.5 text-left">权益</th>
              <th className="py-1.5 text-right">免费版</th>
              <th className="py-1.5 text-right text-gold">Pro</th>
            </tr>
          </thead>
          <tbody>
            {PRO_BENEFITS.map((b) => (
              <tr key={b.label} className="border-b border-paper/50">
                <td className="py-1.5 text-muted-foreground">{b.label}</td>
                <td className="py-1.5 text-right font-mono text-muted-foreground/70">{b.free}</td>
                <td className="py-1.5 text-right font-mono text-foreground">
                  <span className="inline-flex items-center gap-1">
                    <Check className="h-3 w-3 text-up" />{b.pro}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* 支付遇到问题 → 工单(技术故障客服通道)*/}
      <div className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-paper bg-surface-card px-4 py-3">
        <span className="text-sm text-muted-foreground">
          支付遇到问题?(未到账 / 重复扣款 / 开通失败)
        </span>
        <button
          type="button"
          onClick={() => setShowSupport(true)}
          className="text-sm font-medium text-midas-red hover:underline"
        >
          联系客服
        </button>
      </div>

      {payPeriod && (
        <PaymentDialog period={payPeriod} onClose={() => setPayPeriod(null)} />
      )}
      {showSupport && <SupportTicketDialog onClose={() => setShowSupport(false)} />}
    </div>
  )
}

// 兑换码框(套餐排第 4 框 · 与月/季/年同卡片样式)· 复用 /redeem 兑换逻辑(原 RedeemCard 整合)
function RedeemPlanCard() {
  const { data: session } = useSession()
  const token = session?.accessToken ?? ''
  const invalidateQuota = useInvalidateQuota()
  const [code, setCode] = useState('')

  const redeem = useMutation({
    mutationFn: () => redeemCode(token, code.trim()),
    onSuccess: (res) => {
      toast.success(redeemSuccessText(res))
      setCode('')
      invalidateQuota() // 额度卡 plan/到期日即时刷新(逻辑不变)
    },
    onError: (err) => {
      const friendly = err instanceof RedeemApiError ? redeemErrorText(err.detail) : null
      toast.error(friendly ?? '兑换失败,请稍后重试')
    },
  })

  return (
    <div className="flex flex-col rounded-2xl border border-paper bg-background p-5 shadow-sm">
      <div className="flex items-center gap-1.5">
        <Ticket className="h-4 w-4 text-midas-red" />
        <span className="font-serif text-base font-bold">兑换码</span>
      </div>
      <p className="mt-1 text-[11px] text-muted-foreground/70">输入兑换码开通 / 续期 Pro</p>
      <input
        value={code}
        onChange={(e) => setCode(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === 'Enter' && code.trim() !== '') redeem.mutate()
        }}
        placeholder="输入兑换码"
        maxLength={32}
        className="mt-3 min-h-9 w-full rounded-md border border-paper bg-surface-card px-2.5 font-mono text-sm uppercase tracking-wider focus:border-gold focus:outline-none"
      />
      <button
        type="button"
        onClick={() => redeem.mutate()}
        disabled={redeem.isPending || code.trim() === '' || token === ''}
        className="mt-auto rounded-md border border-midas-red py-2 text-sm font-medium text-midas-red transition-colors hover:bg-midas-red-glow disabled:opacity-60"
      >
        {redeem.isPending ? '兑换中…' : '兑换'}
      </button>
    </div>
  )
}
