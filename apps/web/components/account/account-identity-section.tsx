'use client'

/**
 * 账户身份区(个人中心)· 头像(+ 预设选择器)+ 邮箱/用户ID + 修改密码。
 *
 * 🔴 红线:头像零图片存储(只选预设编号 · 不上传)· 密码明文不持久化 ·
 * OAuth-only 用户(has_password=false)不显示改密码表单(显示 Google 提示)。
 */

import { Loader2 } from 'lucide-react'
import { useState } from 'react'
import { toast } from 'sonner'

import { UserAvatar } from '@/components/account/user-avatar'
import { useChangePassword, useMe, useSetAvatar } from '@/hooks/use-me'
import { MeApiError } from '@/lib/api/me'
import { AVATAR_IDS, isPresetAvatar } from '@/lib/avatars'
import { cn } from '@/lib/utils'

const MIN_PW = 8

export function AccountIdentitySection() {
  const { data: me } = useMe()
  const [showPicker, setShowPicker] = useState(false)
  const [showPwForm, setShowPwForm] = useState(false)

  return (
    <section className="mb-10">
      <h2 className="mb-3 font-serif text-xl font-bold text-foreground">账户基本信息</h2>
      <div className="rounded-lg border border-paper bg-cream p-5 shadow-sm">
        {/* 头像 + 邮箱/ID + 更换头像 */}
        <div className="flex items-center gap-4">
          <UserAvatar email={me?.email} avatarId={me?.avatar_id} size={56} />
          <div className="min-w-0 flex-1">
            <p className="truncate font-mono text-sm text-foreground">{me?.email ?? '—'}</p>
            <p className="truncate font-mono text-[11px] text-muted-foreground/70">
              ID {me?.user_id ?? '—'}
            </p>
          </div>
          <button
            type="button"
            onClick={() => setShowPicker((v) => !v)}
            className="shrink-0 rounded-md border border-paper px-3 py-1.5 text-xs text-muted-foreground transition-colors hover:border-gold hover:text-gold"
          >
            更换头像
          </button>
        </div>

        {showPicker && <AvatarPicker email={me?.email} current={me?.avatar_id ?? null} />}

        {/* 修改密码 / OAuth 提示 */}
        <div className="mt-4 border-t border-paper pt-4">
          {me && !me.has_password ? (
            <p className="text-xs leading-relaxed text-muted-foreground">
              你通过 Google 登录,账户安全由 Google 管理(无需在此设置密码)。
            </p>
          ) : !showPwForm ? (
            <button
              type="button"
              onClick={() => setShowPwForm(true)}
              className="text-sm font-medium text-midas-red hover:underline"
            >
              修改密码
            </button>
          ) : (
            <ChangePasswordForm onDone={() => setShowPwForm(false)} />
          )}
        </div>
      </div>
    </section>
  )
}

// ── 头像选择器(默认首字母 + 16 预设 · 占位图)──────────────────────────────────

function AvatarPicker({ email, current }: { email?: string | null; current: number | null }) {
  const setAvatar = useSetAvatar()

  function choose(id: number) {
    if (setAvatar.isPending) return
    setAvatar.mutate(id, {
      onSuccess: () => toast.success('头像已更新'),
      onError: () => toast.error('头像更新失败,请重试'),
    })
  }

  return (
    <div className="mt-4 rounded-md border border-paper bg-background p-3">
      <p className="mb-2 text-[11px] text-muted-foreground/70">
        选择头像(当前为占位图 · 设计版稍后上线)
      </p>
      <div className="grid grid-cols-6 gap-3 sm:grid-cols-9">
        {/* 默认 = 邮箱首字母 */}
        <button
          type="button"
          onClick={() => choose(0)}
          aria-label="默认头像(首字母)"
          className={cn(
            'rounded-full ring-offset-2 ring-offset-background',
            !isPresetAvatar(current) && 'ring-2 ring-midas-red',
          )}
        >
          <UserAvatar email={email} avatarId={null} size={40} />
        </button>
        {AVATAR_IDS.map((id) => (
          <button
            type="button"
            key={id}
            onClick={() => choose(id)}
            aria-label={`头像 ${id}`}
            className={cn(
              'rounded-full ring-offset-2 ring-offset-background',
              current === id && 'ring-2 ring-midas-red',
            )}
          >
            <UserAvatar avatarId={id} size={40} />
          </button>
        ))}
      </div>
    </div>
  )
}

// ── 修改密码表单(旧 + 新 + 确认 · 前端先校验)──────────────────────────────────

function ChangePasswordForm({ onDone }: { onDone: () => void }) {
  const change = useChangePassword()
  const [oldPw, setOldPw] = useState('')
  const [newPw, setNewPw] = useState('')
  const [confirm, setConfirm] = useState('')

  function submit() {
    if (!oldPw) {
      toast.error('请输入当前密码')
      return
    }
    if (newPw.length < MIN_PW) {
      toast.error(`新密码至少 ${MIN_PW} 位`)
      return
    }
    if (newPw !== confirm) {
      toast.error('两次输入的新密码不一致')
      return
    }
    change.mutate(
      { oldPassword: oldPw, newPassword: newPw },
      {
        onSuccess: () => {
          toast.success('密码已修改')
          onDone()
        },
        onError: (e) =>
          toast.error(e instanceof MeApiError ? e.detail : '修改失败,请稍后重试'),
      },
    )
  }

  const inputCls =
    'w-full rounded-md border border-paper bg-background px-3 py-2 text-sm focus:border-gold focus:outline-none'

  return (
    <div className="space-y-2">
      <p className="text-xs font-medium text-foreground">修改密码</p>
      <input
        type="password"
        value={oldPw}
        onChange={(e) => setOldPw(e.target.value)}
        placeholder="当前密码"
        autoComplete="current-password"
        className={inputCls}
      />
      <input
        type="password"
        value={newPw}
        onChange={(e) => setNewPw(e.target.value)}
        placeholder={`新密码(至少 ${MIN_PW} 位)`}
        autoComplete="new-password"
        className={inputCls}
      />
      <input
        type="password"
        value={confirm}
        onChange={(e) => setConfirm(e.target.value)}
        placeholder="确认新密码"
        autoComplete="new-password"
        className={inputCls}
      />
      <div className="flex gap-2 pt-1">
        <button
          type="button"
          onClick={submit}
          disabled={change.isPending}
          className="inline-flex items-center gap-1.5 rounded-md bg-midas-red px-4 py-1.5 text-xs font-medium text-white transition-colors hover:bg-midas-red-deep disabled:opacity-60"
        >
          {change.isPending && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
          保存
        </button>
        <button
          type="button"
          onClick={onDone}
          className="rounded-md border border-paper px-4 py-1.5 text-xs text-muted-foreground hover:bg-cream"
        >
          取消
        </button>
      </div>
    </div>
  )
}
