'use client'

/**
 * 兑换码卡(兑换码刀2 · 个人中心模块)。
 *
 * 输入码 → POST /redeem → 成功 toast + 即时刷新额度卡(plan/到期日)。
 * 三态错误友好提示(后端 404/409/410 结构化 detail · 形状不符走通用,不误判)。
 */

import { useMutation } from '@tanstack/react-query'
import { Ticket } from 'lucide-react'
import { useSession } from 'next-auth/react'
import { useState } from 'react'
import { toast } from 'sonner'

import { useInvalidateQuota } from '@/hooks/use-quota'
import { RedeemApiError, redeemCode } from '@/lib/api/redeem'
import { redeemErrorText, redeemSuccessText } from '@/lib/redeem-view'

export function RedeemCard() {
  const { data: session } = useSession()
  const token = session?.accessToken ?? ''
  const invalidateQuota = useInvalidateQuota()
  const [code, setCode] = useState('')

  const redeem = useMutation({
    mutationFn: () => redeemCode(token, code.trim()),
    onSuccess: (res) => {
      toast.success(redeemSuccessText(res))
      setCode('')
      invalidateQuota() // 额度卡 plan/到期日即时刷新
    },
    onError: (err) => {
      // 三态:后端结构化 detail → 友好;形状不符 → 通用(不误判)
      const friendly = err instanceof RedeemApiError ? redeemErrorText(err.detail) : null
      toast.error(friendly ?? '兑换失败,请稍后重试')
    },
  })

  return (
    <section className="mb-10">
      <h2 className="mb-3 font-serif text-xl font-bold text-foreground">兑换码</h2>
      <div className="rounded-lg border border-paper bg-cream p-5 shadow-sm">
        <div className="mb-2 flex items-center gap-2 text-sm text-muted-foreground">
          <Ticket className="h-4 w-4 text-midas-red" />
          输入兑换码开通 / 续期 Pro 会员
        </div>
        <div className="flex flex-col gap-3 sm:flex-row">
          <input
            value={code}
            onChange={(e) => setCode(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && code.trim() !== '') redeem.mutate()
            }}
            placeholder="输入兑换码"
            maxLength={32}
            className="min-h-11 flex-1 rounded-md border border-paper bg-background px-3 font-mono text-sm uppercase tracking-wider"
          />
          <button
            type="button"
            onClick={() => redeem.mutate()}
            disabled={redeem.isPending || code.trim() === '' || token === ''}
            className="min-h-11 rounded-md bg-midas-red px-6 text-sm font-medium text-white transition-colors hover:bg-midas-red/90 disabled:opacity-60"
          >
            {redeem.isPending ? '兑换中…' : '兑换'}
          </button>
        </div>
      </div>
    </section>
  )
}
