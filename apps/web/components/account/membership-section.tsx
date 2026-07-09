'use client'

/**
 * 会员订阅区(/account/membership)· 当前档 + 月/季/年 + 其他购买方式(闲鱼)+ 兑换码 + 权益对比 + 客服。
 *
 * 价格如实(USDT)· 已是 Pro 显到期日 + 续费;免费版引导升级。开权益由后端回调核验。
 * 标题保留「会员 · 支持者计划」· 兑换码复用 /redeem 逻辑。
 * ★其他购买方式:给不便用加密支付的用户一条法币通道(闲鱼买会员兑换码)· 中性表述(教育+工具定位)。
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

// ★闲鱼购买入口数据源(Hans 确认后填):
//   · 给【链接】→ 填 XIANYU_SHOP_URL,前端用 qrcode.react 动态生成二维码;
//   · 给【图片】→ 填 XIANYU_QR_IMAGE(如 '/xianyu-qr.png' 放 public/,优先级高于链接);
//   · 二者都空 → 显占位框(区块架子/布局已就位,补数据即上线,无需再改结构)。
const XIANYU_SHOP_URL: string = ''
const XIANYU_QR_IMAGE: string = ''

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

      {/* ★B · 其他购买方式(闲鱼法币通道)· 价格卡下方、兑换码上方 · 中性表述(教育+工具定位)*/}
      <OtherPurchaseBlock />

      {/* 兑换码(承接闲鱼购买 → 填码开通)· 复用 /redeem 兑换逻辑 */}
      <RedeemPlanCard />

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

// ★B · 其他购买方式(闲鱼法币通道)· 中性表述(不用「绕过/规避支付」「更便宜」等词 · 守教育+工具红线)
function OtherPurchaseBlock() {
  return (
    <div className="rounded-lg border border-paper bg-surface-card p-5">
      <div className="flex items-center gap-1.5 text-sm font-medium text-foreground">
        <Store className="h-4 w-4 text-midas-red" /> 其他购买方式
      </div>
      <p className="mt-1.5 text-sm text-muted-foreground">
        不便使用加密支付?可通过闲鱼购买会员兑换码。
      </p>
      <div className="mt-4 flex flex-col items-center gap-3 sm:flex-row sm:items-start sm:gap-5">
        <XianyuQr />
        <p className="text-center text-xs text-muted-foreground sm:pt-1 sm:text-left">
          扫码进店购买 · 购买后将兑换码填入下方开通。
        </p>
      </div>
    </div>
  )
}

// 闲鱼二维码:优先图片 → 其次链接动态生成(qrcode.react)→ 都无则占位(架子就位·补数据即上线)
function XianyuQr() {
  const box = 'flex h-32 w-32 shrink-0 items-center justify-center rounded-lg border border-paper bg-background'
  if (XIANYU_QR_IMAGE) {
    // eslint-disable-next-line @next/next/no-img-element -- 静态店铺二维码·非内容图·不走 next/image
    return <img src={XIANYU_QR_IMAGE} alt="闲鱼店铺二维码" className="h-32 w-32 rounded-lg border border-paper" />
  }
  if (XIANYU_SHOP_URL) {
    return (
      <div className={box}>
        <QRCodeSVG value={XIANYU_SHOP_URL} size={112} level="M" />
      </div>
    )
  }
  return (
    <div className={`${box} px-2 text-center text-[11px] leading-tight text-muted-foreground/70`}>
      闲鱼店铺二维码
      <br />
      即将上线
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
        {/* ★C · 引导:还没有兑换码 → 指向上方「其他购买方式」闲鱼入口 */}
        <span className="ml-auto text-[11px] text-midas-red">
          还没有兑换码?可在上方「其他购买方式」经闲鱼购买 ↑
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
