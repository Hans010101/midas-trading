'use client'

/**
 * 邀请有礼(用户中心模块⑤ · Phase 1.5 刀B)。
 *
 * 我的邀请码 + 邀请链接(★ 复制链接为主操作)+ 奖励说明 + 统计(GET /invite/me)。
 * 海报入口本刀占位(刀C 接 canvas)。
 */

import { Check, Copy, Gift } from 'lucide-react'
import { useState } from 'react'

import { useInvite } from '@/hooks/use-invite'

function CopyButton({ text, label, primary = false }: {
  text: string
  label: string
  primary?: boolean
}) {
  const [copied, setCopied] = useState(false)
  async function copy() {
    try {
      await navigator.clipboard.writeText(text)
      setCopied(true)
      setTimeout(() => setCopied(false), 1800)
    } catch {
      // clipboard 不可用(http/老浏览器)· 静默 · 用户可手动选中复制
    }
  }
  return (
    <button
      type="button"
      onClick={copy}
      className={
        primary
          ? 'inline-flex min-h-10 items-center gap-1.5 rounded-md bg-midas-red px-4 text-sm font-medium text-white transition-colors hover:bg-midas-red/90'
          : 'inline-flex min-h-10 items-center gap-1.5 rounded-md border border-paper px-3 text-sm text-muted-foreground transition-colors hover:text-foreground'
      }
    >
      {copied ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
      {copied ? '已复制' : label}
    </button>
  )
}

export default function InvitePage() {
  const invite = useInvite()
  const data = invite.data

  return (
    <div>
      <h1 className="mb-6 font-serif text-2xl font-bold text-foreground">邀请有礼</h1>

      {/* 奖励说明(诚实文案:验证后到账 · 15 天 · 90 天上限) */}
      <div className="mb-6 flex items-start gap-3 rounded-lg border border-gold/40 bg-gold/10 p-4">
        <Gift className="mt-0.5 h-5 w-5 shrink-0 text-gold" />
        <p className="text-sm leading-relaxed text-foreground">
          好友通过你的链接注册并完成邮箱验证后,
          <strong className="text-gold">双方各得 15 天 Pro</strong>
          ,可累积至 90 天上限。
        </p>
      </div>

      {data === undefined ? (
        <p className="text-sm text-muted-foreground/60">
          {invite.status === 'error' ? '邀请信息读取失败,稍后重试' : '加载中…'}
        </p>
      ) : (
        <div className="space-y-6">
          {/* 邀请链接(主操作)+ 邀请码 */}
          <div className="rounded-lg border border-paper bg-cream p-5 shadow-sm">
            <div className="mb-1 text-xs text-muted-foreground">我的邀请链接</div>
            <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
              <code className="min-w-0 flex-1 truncate rounded bg-surface-subtle px-3 py-2 font-mono text-sm text-foreground">
                {data.invite_url}
              </code>
              <CopyButton text={data.invite_url} label="复制链接" primary />
            </div>
            <div className="mt-4 flex items-center justify-between border-t border-paper/60 pt-4">
              <div>
                <div className="text-xs text-muted-foreground">邀请码</div>
                <div className="font-mono text-2xl font-bold tracking-wider text-midas-red">
                  {data.code}
                </div>
              </div>
              <CopyButton text={data.code} label="复制码" />
            </div>
          </div>

          {/* 统计 */}
          <div className="grid grid-cols-3 gap-3">
            <StatCard label="已邀请" value={data.invited_count} unit="人" />
            <StatCard label="已兑现" value={data.rewarded_count} unit="人" />
            <StatCard label="累计获赠" value={data.earned_days} unit="天" />
          </div>

          {/* 海报入口(刀C 占位) */}
          <button
            type="button"
            disabled
            className="min-h-10 rounded-md border border-dashed border-paper px-4 text-sm text-muted-foreground/50"
          >
            生成邀请海报 · 即将上线
          </button>
        </div>
      )}
    </div>
  )
}

function StatCard({ label, value, unit }: { label: string; value: number; unit: string }) {
  return (
    <div className="rounded-lg border border-paper bg-cream p-4 text-center shadow-sm">
      <div className="font-mono text-2xl font-bold tabular-nums text-foreground">{value}</div>
      <div className="mt-1 text-xs text-muted-foreground">
        {label} · {unit}
      </div>
    </div>
  )
}
