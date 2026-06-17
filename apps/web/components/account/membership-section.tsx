'use client'

/**
 * 会员订阅区(Phase 2a 刀2 · /account/membership)· 当前档 + 三档定价 + 支持者叙事 + 权益对比。
 *
 * 叙事:诚实订阅(付 X 得 Pro 全部更高额度,到期回落免费版,无自动续费)+「支持者计划」品牌温度。
 * 价格如实(USDT)· 已是 Pro 显到期日 + 续费;免费版引导升级。开权益由后端回调核验。
 */

import { Check, Sparkles } from 'lucide-react'
import { useState } from 'react'

import { useQuota } from '@/hooks/use-quota'
import { type Period } from '@/lib/api/payment'
import {
  monthlyEquivalent,
  PLAN_TIERS,
  PRO_BENEFITS,
  savingsPct,
  SUPPORTER_NOTE,
} from '@/lib/payment-plans'
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
      {/* 标题 + 支持者叙事 */}
      <div>
        <h2 className="font-serif text-xl font-bold text-foreground">会员 · 支持者计划</h2>
        <p className="mt-2 max-w-2xl text-sm leading-relaxed text-muted-foreground">{SUPPORTER_NOTE}</p>
      </div>

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

      {/* 三档定价 */}
      <div className="grid gap-4 sm:grid-cols-3">
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
        <p className="mt-3 text-[11px] leading-relaxed text-muted-foreground/60">
          到期后自动回落免费版(额度恢复免费档)· 无自动续费 · 续费在有效期内累加不浪费。
        </p>
      </div>

      {/* 支付遇到问题 → 工单 / 退款入口 */}
      <div className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-paper bg-surface-card px-4 py-3">
        <span className="text-sm text-muted-foreground">
          支付遇到问题?(未到账 / 重复扣款 / 申请退款)
        </span>
        <button
          type="button"
          onClick={() => setShowSupport(true)}
          className="text-sm font-medium text-midas-red hover:underline"
        >
          联系客服 / 申请退款
        </button>
      </div>

      {payPeriod && (
        <PaymentDialog period={payPeriod} onClose={() => setPayPeriod(null)} />
      )}
      {showSupport && <SupportTicketDialog onClose={() => setShowSupport(false)} />}
    </div>
  )
}
