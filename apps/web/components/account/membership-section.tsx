'use client'

/**
 * 会员订阅区(/account/membership)· 当前档 + 月/季/年 + 其他购买方式(闲鱼)+ 兑换码 + 权益对比 + 客服。
 *
 * 价格如实(USDT)· 已是 Pro 显到期日 + 续费;免费版引导升级。开权益由后端回调核验。
 * 标题保留「会员 · 支持者计划」· 兑换码复用 /redeem 逻辑。
 * ★布局主次(Hans 定):加密支付=主角(价格卡最上·卡内零二维码不被干扰)→ 兑换码框 →
 *   「其他购买方式」=配角沉底(三 SKU 闲鱼二维码集中·月/季/年各带标签·视觉低调)。
 *   一商品一链接 · 中性表述(教育+工具定位)。
 */

import { useMutation } from '@tanstack/react-query'
import { Check, Sparkles, Store, Ticket } from 'lucide-react'
import { useSession } from 'next-auth/react'
import { useState } from 'react'
import { QRCodeSVG } from 'qrcode.react'
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

// ★闲鱼购买链接(Hans 提供 2026-07-09):一商品一链接 · 月/季/年三 SKU 各自二维码
//   (方案 A · 就近对应:每个价格卡底部放该档二维码,看哪档扫哪档)。换链接改这里即可。
const XIANYU_URLS: Record<Period, string> = {
  month: 'https://m.tb.cn/h.RByCLbN?tk=B3a1go3qzBV',
  quarter: 'https://m.tb.cn/h.RByBLUA?tk=W2R9go3IYoY',
  year: 'https://m.tb.cn/h.RBBbl2Q?tk=WUdxgo3uErc',
}

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

      {/* 三档定价(月/季/年 · 宽屏 3 / 中屏 2 / 窄屏堆叠)· 兑换码/其他购买方式移到下方竖排 */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
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

      {/* 兑换码(输入兑换码开通)· 复用 /redeem 兑换逻辑 */}
      <RedeemPlanCard />

      {/* ★其他购买方式(闲鱼法币通道·辅助区)· ★沉底配角:加密支付主角在上、卡内零二维码
          不干扰主推路径;三 SKU 码集中此框 · 中性表述(教育+工具定位)*/}
      <OtherPurchaseBlock />

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

// ★其他购买方式(闲鱼法币通道)· ★辅助区沉底(Hans 定:加密支付主角、闲鱼配角、主次分开):
//   三 SKU 集中此框 · ★双通道覆盖两种设备(手机没法扫自己屏幕的码=硬伤):
//   二维码(电脑用户拿手机闲鱼 App 扫)+ 可点击链接(手机用户点击直达/唤起闲鱼)。
//   视觉低调(muted·不抢主角)· 中性表述(不用「绕过/规避支付」「更便宜」等词)。
function OtherPurchaseBlock() {
  return (
    <div className="rounded-lg border border-paper bg-surface-card p-5">
      <div className="flex items-center gap-1.5 text-sm font-medium text-muted-foreground">
        <Store className="h-4 w-4" /> 其他购买方式
      </div>
      <p className="mt-1.5 text-xs text-muted-foreground">
        不便使用加密支付?可通过闲鱼购买会员兑换码,购买后填入上方兑换码框开通。
      </p>
      <div className="mt-4 flex flex-wrap justify-center gap-6 sm:justify-start">
        {PLAN_TIERS.map((t) => (
          <div key={t.period} className="flex flex-col items-center gap-1.5">
            <div className="rounded-md border border-paper bg-white p-1.5">
              <QRCodeSVG value={XIANYU_URLS[t.period]} size={96} level="M" />
            </div>
            <span className="text-[11px] text-muted-foreground">{t.label}</span>
            {/* ★手机通道:点击直达对应闲鱼商品(手机扫不了自己屏幕的码) */}
            <a
              href={XIANYU_URLS[t.period]}
              target="_blank"
              rel="noopener noreferrer"
              className="rounded-md border border-paper px-2.5 py-1 text-[11px] text-muted-foreground transition-colors hover:border-midas-red/40 hover:text-foreground"
            >
              打开闲鱼购买{t.label} ↗
            </a>
          </div>
        ))}
      </div>
      <p className="mt-3 text-center text-[10px] text-muted-foreground/70 sm:text-left">
        电脑端:请用闲鱼 App 扫对应二维码 · 手机端:点「打开闲鱼购买」直达 ·
        月度 / 季度 / 年度各自独立商品
      </p>
    </div>
  )
}

// 兑换码(承接闲鱼购买 → 填码开通 · 全宽块 · 复用 /redeem 兑换逻辑)
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
    <div className="rounded-lg border border-paper bg-surface-card p-5">
      <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
        <div className="flex items-center gap-1.5">
          <Ticket className="h-4 w-4 text-midas-red" />
          <span className="font-serif text-base font-bold">兑换码</span>
        </div>
        <span className="text-[11px] text-muted-foreground/70">输入兑换码开通 / 续期 Pro</span>
        {/* ★C · 引导:还没有兑换码 → 指向下方「其他购买方式」(闲鱼三码就在紧下方)*/}
        <span className="ml-auto text-[11px] text-muted-foreground">
          还没有兑换码?见下方「其他购买方式」经闲鱼购买 ↓
        </span>
      </div>
      <div className="mt-3 flex flex-col gap-2 sm:flex-row">
        <input
          value={code}
          onChange={(e) => setCode(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && code.trim() !== '') redeem.mutate()
          }}
          placeholder="输入兑换码"
          maxLength={32}
          className="min-h-9 flex-1 rounded-md border border-paper bg-background px-2.5 font-mono text-sm uppercase tracking-wider focus:border-gold focus:outline-none"
        />
        <button
          type="button"
          onClick={() => redeem.mutate()}
          disabled={redeem.isPending || code.trim() === '' || token === ''}
          className="rounded-md border border-midas-red py-2 text-sm font-medium text-midas-red transition-colors hover:bg-midas-red-glow disabled:opacity-60 sm:px-8"
        >
          {redeem.isPending ? '兑换中…' : '兑换'}
        </button>
      </div>
    </div>
  )
}
